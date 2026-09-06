// Stable session IDs are references, not a request to reroute a prompt.
export function sessionMentionQuery(text, caret) {
    const before = String(text).slice(0, caret);
    const match = before.match(/(?:^|\s)@([^\s@]*)$/);
    return match ? { query: match[1], start: before.length - match[1].length - 1, end: before.length } : null;
}

export function sessionMentionMatches(sessions, query) {
    const needle = query.toLowerCase();
    return sessions.filter(item => !item.archived && `${item.name} ${item.id}`.toLowerCase().includes(needle)).slice(0, 10);
}

export function insertSessionMention(text, range, sessionId) {
    return text.slice(0, range.start) + `@session:${sessionId} ` + text.slice(range.end);
}
