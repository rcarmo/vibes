"""Stdio message reads and optional capability-scoped attachment delivery."""
import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from urllib.parse import urlsplit
import aiohttp
from pathlib import Path

import aiosqlite
from vibes.message_tools import MessageTools
from vibes.workspace_tools import WorkspaceTools
from vibes._vendor.umcp.aioumcp import AsyncMCPServer

TOOL = {
    'name': 'messages',
    'description': 'Retrieve message references by row ID or search message text within the configured scope. Use action=attachment with media_id to read bounded text previews of uploads referenced in scope. Binary uploads return metadata only. Read-only, bounded and paginated.',
    'inputSchema': {
        'type': 'object', 'additionalProperties': False, 'required': ['action'],
        'properties': {
            'action': {'type': 'string', 'enum': ['get', 'search', 'attachment', 'resolve_session']},
            'row_ids': {'type': 'array', 'minItems': 1, 'maxItems': 50, 'items': {'type': 'integer', 'minimum': 1}},
            'query': {'type': 'string', 'maxLength': 500},
            'reference': {'type': 'string', 'maxLength': 521, 'description': '@session:ID for resolve_session; identity only within existing scope, never grants history access. Unauthorized and missing references both return null'},
            'media_id': {'type': 'integer', 'minimum': 1},
            'limit': {'type': 'integer', 'minimum': 1, 'maximum': 50, 'default': 10},
            'before_row': {'type': 'integer', 'minimum': 1, 'description': 'Exclusive upper row boundary; combine with after_row for a bounded range'},
            'after_row': {'type': 'integer', 'minimum': 1, 'description': 'Exclusive lower row boundary; when combined, must be less than before_row'},
            'context_before': {'type': 'integer', 'minimum': 0, 'maximum': 20, 'default': 0},
            'context_after': {'type': 'integer', 'minimum': 0, 'maximum': 20, 'default': 0},
        },
    },
    'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'openWorldHint': False},
}


ATTACH_DESCRIPTION = 'Attach a workspace image or file (up to 10 MB) to this chat immediately. Returns a durable media ID and attachment: reference. No base64 or copying into the final answer is needed. Raster images display inline; SVG and other files are downloads.'
ATTACH_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['path'], 'properties': {
    'path': {'type': 'string', 'maxLength': 4096}, 'name': {'type': 'string', 'maxLength': 255},
    'content_type': {'type': 'string', 'maxLength': 100}, 'kind': {'type': 'string', 'enum': ['image', 'file']},
    'request_id': {'type': 'string', 'maxLength': 200, 'description': 'Stable ID when retrying the same attachment'},
}}


class MessagesMCP(AsyncMCPServer):
    def _setup_logging(self):
        # Never create vendor-directory log files or put diagnostics on stdout.
        self.logger = logging.getLogger('vibes.messages_mcp')

    def __init__(self, tools, workspace_root=None, attachment_url=None, attachment_token=None, attachment_session=None):
        super().__init__()
        self.tools = tools
        self.attachment_url, self.attachment_token = attachment_url, attachment_token
        if attachment_url and attachment_token and (attachment_session or tools and tools.session_id):
            parsed = urlsplit(attachment_url)
            if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', '::1') or parsed.path != '/internal/agent-tools/attach-file':
                raise ValueError('Attachment endpoint must be the local Vibes service')
            self.register_tool('attach_file', self.attach_file, description=ATTACH_DESCRIPTION, input_schema=ATTACH_SCHEMA,
                               annotations={'readOnlyHint': False, 'destructiveHint': False})
            self.register_tool('plan', self.plan,
                description='Read/update the shared current-session Plan sidebar (max128KiB). Read first; mutations require expected_revision. update uses plan:[{step,status:pending|in_progress|completed}]. patch uses patches:[{operation:add|update|remove,index:1-based OR match:unique,step?,status?,position:start|end}]. edit uses edits:[{operation:replace|delete|insert_before|insert_after|append|prepend,oldText?,newText?,text?,anchorText?}], exact anchors only. At most one in-progress item; destination is bound to the active turn.',
                input_schema={'type': 'object', 'additionalProperties': False, 'required': ['action'], 'properties': {
                    'action': {'type': 'string', 'enum': ['read', 'write', 'update', 'patch', 'edit']},
                    'expected_revision': {'type': 'integer', 'minimum': 0}, 'markdown': {'type': 'string'},
                    'plan': {'type': 'array', 'items': {'type': 'object'}},
                    'patches': {'type': 'array', 'items': {'type': 'object'}},
                    'edits': {'type': 'array', 'items': {'type': 'object'}},
                }}, annotations={'readOnlyHint': False, 'destructiveHint': False})
        self.workspace = WorkspaceTools(workspace_root) if workspace_root else None
        if self.workspace:
            self.register_tool('workspace_list', self.workspace_list,
                description='List a bounded relative workspace directory without following symlinks. Root is dot; truncated listings are not exhaustive.',
                input_schema={'type': 'object', 'additionalProperties': False, 'properties': {
                    'path': {'type': 'string', 'default': '.'},
                    'limit': {'type': 'integer', 'minimum': 1, 'maximum': 200, 'default': 100}}},
                annotations={'readOnlyHint': True, 'destructiveHint': False})
            self.register_tool('workspace_read', self.workspace_read,
                description='Read a bounded text preview of a relative workspace file. Byte offsets paginate. Symlinks and traversal are rejected.',
                input_schema={'type': 'object', 'additionalProperties': False, 'required': ['path'], 'properties': {
                    'path': {'type': 'string'}, 'offset': {'type': 'integer', 'minimum': 0},
                    'limit': {'type': 'integer', 'minimum': 1, 'maximum': 24000}}},
                annotations={'readOnlyHint': True, 'destructiveHint': False})
        if tools is not None:
            self.register_tool('messages', self.messages,
                description=TOOL['description'], input_schema=TOOL['inputSchema'],
                annotations=TOOL['annotations'])

    async def plan(self, action, expected_revision=None, markdown=None, plan=None, patches=None, edits=None):
        fields = {'read': set(), 'write': {'markdown'}, 'update': {'plan'}, 'patch': {'patches'}, 'edit': {'edits'}}
        allowed = {'action', 'expected_revision'} | fields.get(action, set())
        params = {key: value for key, value in {'action': action, 'expected_revision': expected_revision,
                  'markdown': markdown, 'plan': plan, 'patches': patches, 'edits': edits}.items() if value is not None and key in allowed}
        url = self.attachment_url.removesuffix('/attach-file') + '/plan'
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as client:
            async with client.post(url, json=params, headers={'Authorization': 'Bearer ' + self.attachment_token}) as response:
                result = await response.json()
                if response.status >= 400:
                    raise ValueError(result.get('error', 'Plan operation failed'))
                return result

    async def attach_file(self, path: str, name=None, content_type=None, kind=None, request_id=None):
        params = {key: value for key, value in {'path': path, 'name': name, 'content_type': content_type,
                  'kind': kind, 'request_id': request_id or uuid.uuid4().hex}.items() if value is not None}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as client:
            async with client.post(self.attachment_url, json=params, headers={'Authorization': 'Bearer ' + self.attachment_token}) as response:
                result = await response.json()
                if response.status >= 400:
                    raise ValueError(result.get('error', 'Attachment failed'))
                return result

    async def workspace_list(self, path: str = '.', limit: int = 100):
        if not self.workspace:
            raise ValueError('Workspace access not configured')
        return await asyncio.to_thread(self.workspace.list_directory, path, limit)

    async def workspace_read(self, path: str, offset: int = 0, limit: int = 24000):
        if not self.workspace:
            raise ValueError('Workspace access not configured')
        return await asyncio.to_thread(self.workspace.read, path, offset, limit)

    async def messages(self, action: str, row_ids=None, query: str = '', limit: int = 10, before_row=None,
                       after_row=None, context_before: int = 0, context_after: int = 0, media_id=None, reference=None):
        return await self.tools.query(action, row_ids=row_ids, query=query, limit=limit,
            before_row=before_row, after_row=after_row, context_before=context_before,
            context_after=context_after, media_id=media_id, reference=reference)

    async def handle(self, request):
        return await self.process_request_async(json.dumps(request))


async def serve(database, thread_id=None, workspace_access=False, workspace_root=None, session_id=None):
    uri = Path(database).resolve().as_uri() + '?mode=ro'
    async with aiosqlite.connect(uri, uri=True) as connection:
        connection.row_factory = aiosqlite.Row
        await connection.execute('PRAGMA query_only=ON')
        server = MessagesMCP(MessageTools(connection, thread_id=thread_id, session_id=session_id, workspace_access=workspace_access), workspace_root,
                             os.environ.get('VIBES_ATTACHMENT_URL'), os.environ.get('VIBES_ATTACHMENT_TOKEN'))
        await serve_requests(server)


async def serve_requests(server):
    while True:
        line = await asyncio.to_thread(sys.stdin.buffer.readline, 65537)
        if not line:
            break
        if len(line) > 65536:
            # Close rather than interpreting fragments of an oversized frame.
            break
        try:
            response = await server.handle(json.loads(line))
        except (ValueError, UnicodeError):
            response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database')
    parser.add_argument('--attachments-only', action='store_true', help='Expose only attachment delivery, with no database read access')
    parser.add_argument('--workspace-root', help='Explicitly enable bounded workspace reads')
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--thread-id', type=int)
    scope.add_argument('--session-id', help='Restrict reads to one durable chat session')
    scope.add_argument('--workspace-access', action='store_true')
    args = parser.parse_args()
    if args.thread_id is not None and args.thread_id < 1:
        parser.error('--thread-id must be positive')
    if args.attachments_only:
        if not args.session_id or not os.environ.get('VIBES_ATTACHMENT_TOKEN') or not os.environ.get('VIBES_ATTACHMENT_URL'):
            parser.error('Attachment delivery requires a session and configured transport')
        server = MessagesMCP(None, attachment_url=os.environ['VIBES_ATTACHMENT_URL'],
                             attachment_token=os.environ['VIBES_ATTACHMENT_TOKEN'], attachment_session=args.session_id)
        asyncio.run(serve_requests(server))
    else:
        if not args.database:
            parser.error('--database is required for message reads')
        asyncio.run(serve(args.database, args.thread_id, args.workspace_access, args.workspace_root, args.session_id))


if __name__ == '__main__':
    main()
