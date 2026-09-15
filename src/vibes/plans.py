"""Durable shared checklists. Browser and model writes use the same revision CAS."""
import asyncio
import re

MAX_PLAN_BYTES = 128 * 1024
CHECKBOX = re.compile(r'^(\s*[-*+]\s+)\[([ xX-])\](\s+)(.*)$')
STATUSES = {'pending': ' ', 'in_progress': '-', 'completed': 'x'}


class PlanConflict(ValueError):
    pass


def checklist_lines(markdown):
    """Ignore fenced examples when normalising real checklist items."""
    fence = None
    for index, line in enumerate(markdown.splitlines()):
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is None:
            match = CHECKBOX.match(line)
            if match:
                yield index, match


def normalize_markdown(markdown):
    if not isinstance(markdown, str) or '\x00' in markdown or len(markdown.encode('utf-8')) > MAX_PLAN_BYTES:
        raise ValueError('Plan must be UTF-8 text of at most 128 KiB without NUL')
    lines = markdown.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    active = False
    for index, match in checklist_lines('\n'.join(lines)):
        state = match[2].lower()
        if state == '-':
            state = ' ' if active else '-'
            active = True
        lines[index] = f'{match[1]}[{state}]{match[3]}{match[4]}'
    return '\n'.join(lines)


def plan_item(item):
    if not isinstance(item, dict) or set(item) - {'step', 'status'}:
        raise ValueError('Expected step/status object')
    step, status = item.get('step'), item.get('status', 'pending')
    if not isinstance(step, str) or not step.strip() or '\n' in step or '\r' in step or status not in STATUSES:
        raise ValueError('Invalid plan step/status')
    return f'- [{STATUSES[status]}] {step.strip()}'


def apply_plan_action(markdown, payload):
    if not isinstance(payload, dict):
        raise ValueError('Expected plan object')
    action = payload.get('action')
    allowed = {'action', 'expected_revision', 'request_id'}
    action_fields = {'read': set(), 'write': {'markdown'}, 'update': {'plan'}, 'patch': {'patches'}, 'edit': {'edits'}}
    if action not in action_fields:
        raise ValueError('Invalid plan action; use read/write/update/patch/edit')
    extra = set(payload) - allowed - action_fields[action]
    if extra:
        raise ValueError('Unexpected fields for ' + action + ': ' + ', '.join(sorted(extra)))
    if action == 'read':
        return markdown
    if action == 'write':
        return normalize_markdown(payload.get('markdown'))
    if action == 'update':
        items = payload.get('plan')
        if not isinstance(items, list) or len(items) > 1000:
            raise ValueError('Expected at most 1000 plan items')
        return normalize_markdown('\n'.join(plan_item(item) for item in items))
    operations = payload.get('patches' if action == 'patch' else 'edits')
    if not isinstance(operations, list) or not 1 <= len(operations) <= 100:
        raise ValueError('Expected 1-100 operations')
    for item in operations:
        if not isinstance(item, dict):
            raise ValueError('Expected operation object')
        operation = item.get('operation', 'replace' if action == 'edit' else '')
        if action == 'patch':
            if set(item) - {'operation', 'index', 'match', 'step', 'status', 'position'}:
                raise ValueError('Invalid patch fields')
            lines = markdown.split('\n')
            entries = list(checklist_lines(markdown))
            if operation == 'add':
                new = plan_item({key: item[key] for key in ('step', 'status') if key in item})
                if item.get('position', 'end') not in ('start', 'end'):
                    raise ValueError('Invalid patch position')
                lines.insert(0 if item.get('position') == 'start' else len(lines), new)
            else:
                if operation not in ('update', 'remove'):
                    raise ValueError('Invalid patch operation')
                if 'index' in item and 'match' in item:
                    raise ValueError('Use index or match, not both')
                index = item.get('index')
                if 'match' in item:
                    needle = item['match']
                    if not isinstance(needle, str) or not needle:
                        raise ValueError('Nonempty patch match required')
                    found = [i for i, (_, entry) in enumerate(entries) if needle in entry[4]]
                    if len(found) != 1:
                        raise ValueError('Patch match must identify exactly one item')
                    index = found[0] + 1
                if type(index) is not int or not 1 <= index <= len(entries):
                    raise ValueError('Patch index out of range')
                line_index, entry = entries[index - 1]
                if operation == 'remove':
                    del lines[line_index]
                else:
                    old_status = {' ': 'pending', '-': 'in_progress', 'x': 'completed'}[entry[2].lower()]
                    lines[line_index] = plan_item({'step': item.get('step', entry[4]), 'status': item.get('status', old_status)})
            markdown = '\n'.join(lines)
        else:
            if set(item) - {'operation', 'oldText', 'newText', 'text', 'anchorText'}:
                raise ValueError('Invalid edit fields')
            text = item.get('text', item.get('newText', ''))
            if not isinstance(text, str):
                raise ValueError('Edit text must be a string')
            if operation in ('append', 'prepend'):
                markdown = markdown + text if operation == 'append' else text + markdown
            elif operation in ('replace', 'delete', 'insert_before', 'insert_after'):
                anchor = item.get('anchorText') if operation.startswith('insert_') else item.get('oldText')
                if not isinstance(anchor, str) or not anchor or markdown.count(anchor) != 1:
                    raise ValueError('Edit anchor must match exactly once')
                replacement = {'replace': text, 'delete': '', 'insert_before': text + anchor, 'insert_after': anchor + text}[operation]
                markdown = markdown.replace(anchor, replacement, 1)
            else:
                raise ValueError('Invalid edit operation')
        # Check bounds after each operation without erasing later in-progress edits.
        if len(markdown.encode('utf-8')) > MAX_PLAN_BYTES:
            raise ValueError('Plan exceeds 128 KiB')
    return normalize_markdown(markdown)


class PlanStore:
    def __init__(self, db):
        self.db = db
        if not hasattr(db, '_plan_lock'):
            db._plan_lock = asyncio.Lock()

    async def get(self, session_id):
        async with self.db._connection.execute('SELECT p.markdown,p.revision,p.updated_at FROM chat_sessions s LEFT JOIN session_plans p ON p.session_id=s.id WHERE s.id=?', (session_id,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise LookupError('Session not found')
        return {'session_id': session_id, 'markdown': row['markdown'] or '', 'revision': row['revision'] or 0, 'updated_at': row['updated_at']}

    async def apply(self, session_id, payload, *, owner_check=None):
        async with self.db._plan_lock:
            snapshot = await self.get(session_id)
            markdown = apply_plan_action(snapshot['markdown'], payload)
            if owner_check:
                owner_check()
            if payload['action'] == 'read':
                return snapshot
            expected = payload.get('expected_revision', snapshot['revision'])
            if type(expected) is not int or expected < 0:
                raise ValueError('expected_revision must be a nonnegative integer')
            if expected != snapshot['revision']:
                raise PlanConflict('Plan changed; read the latest revision before saving')
            # Single conditional statement protects independent connections as well.
            async with self.db._connection.execute('''
                INSERT INTO session_plans(session_id,markdown,revision)
                SELECT id,?,1 FROM chat_sessions WHERE id=? AND archived=0
                  AND (?=0 OR EXISTS(SELECT 1 FROM session_plans WHERE session_id=chat_sessions.id))
                ON CONFLICT(session_id) DO UPDATE SET markdown=excluded.markdown,
                  revision=session_plans.revision+1,updated_at=CURRENT_TIMESTAMP
                  WHERE session_plans.revision=?
                RETURNING markdown,revision,updated_at
            ''', (markdown, session_id, expected, expected)) as cursor:
                saved = await cursor.fetchone()
            await self.db._connection.commit()
            if saved is None:
                raise PlanConflict('Plan changed or session is archived; reload before saving')
            return {'session_id': session_id, **dict(saved)}
