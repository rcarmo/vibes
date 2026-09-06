import { test, expect } from 'bun:test';
import { groupSessions } from '../../src/vibes/static/js/components/session-groups.js';

test('groups by explicit state and ancestry without inventing running status', () => {
    const rows = [{ id: 'root' }, { id: 'current', parent_id: 'root' }, { id: 'pin', pinned: true }, { id: 'run', is_running: true }, { id: 'old', archived: true }, { id: 'other', last_message_at: '2099-01-01' }];
    const groups = Object.fromEntries(groupSessions(rows, 'current').map(g => [g.label, g.items.map(x => x.id)]));
    expect(groups).toEqual({ Current: ['current'], Pinned: ['pin'], Active: ['run'], Tree: ['root'], Other: ['other'], Archived: ['old'] });
});
