// Group metadata without inferring runtime activity from message timestamps.
export function groupSessions(sessions, currentId) {
    const byId = new Map(sessions.map(item => [item.id, item]));
    const root = id => {
        const seen = new Set();
        while (byId.get(id)?.parent_id && !seen.has(id)) {
            seen.add(id);
            id = byId.get(id).parent_id;
        }
        return id;
    };
    const currentRoot = root(currentId);
    const groups = new Map(['Current', 'Pinned', 'Active', 'Tree', 'Other', 'Archived'].map(name => [name, []]));
    for (const item of sessions) {
        const name = item.archived ? 'Archived' : item.id === currentId ? 'Current'
            : item.pinned ? 'Pinned' : item.is_running === true ? 'Active'
            : root(item.id) === currentRoot ? 'Tree' : 'Other';
        groups.get(name).push(item);
    }
    return [...groups].filter(([, items]) => items.length).map(([label, items]) => ({ label, items }));
}
