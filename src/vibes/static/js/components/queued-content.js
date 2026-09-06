// Display-only parsing: never rewrite the queued payload sent to the agent.
export function parseQueuedContent(content) {
    const lines = String(content || '').split(/\r?\n/);
    const text = [];
    const refs = [];
    let section = null;
    const headers = { 'Files:': 'file', 'Folders:': 'folder', 'Messages:': 'message', 'Referenced messages:': 'message', 'Images:': 'attachment', 'Attachments:': 'attachment' };
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (headers[line.trim()] && /^\s*-\s+/.test(lines[i + 1] || '')) {
            section = headers[line.trim()];
            continue;
        }
        const match = section && line.match(/^\s*-\s+(.+)$/);
        if (match) {
            const value = match[1].trim();
            let ref;
            if (section === 'file' || section === 'folder') {
                const path = value.replace(/^`(.*)`$/, '$1');
                ref = { kind: section, title: path, label: path.split('/').filter(Boolean).pop() || path };
            } else if (section === 'message' && /^(?:message:)?\d+$/.test(value)) {
                ref = { kind: section, label: 'msg:' + value.replace(/^message:/, ''), title: value };
            } else if (section === 'attachment') {
                const attachment = value.match(/^attachment:(\d+)(?:\s*\((.*)\))?$/);
                if (attachment) ref = { kind: section, label: attachment[2] || `attachment:${attachment[1]}`, title: value };
            }
            if (ref && refs.length < 50) { refs.push(ref); continue; }
        } else {
            section = null;
        }
        text.push(line);
    }
    return { text: text.join('\n').trim(), refs };
}
