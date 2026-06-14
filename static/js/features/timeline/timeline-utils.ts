const SAFE_URL_RE = /^(https?:|mailto:|blob:|data:)/i;

export interface BlockRefsResult {
    content: string;
    refs: string[];
}

export interface NamedRefsResult {
    content: string;
    fileRefs?: string[];
    messageRefs?: string[];
}

export interface AttachmentRef {
    id: string | null;
    label: string;
    raw: string;
}

export interface AttachmentRefsResult {
    content: string;
    attachments: AttachmentRef[];
}

export interface AvatarInfo {
    letter: string;
    color: string;
    image: string | null;
}

export function sanitizeUrl(url: unknown): string {
    if (!url || typeof url !== 'string') return '';
    return SAFE_URL_RE.test(url.trim()) ? url.trim() : '';
}

export function escapeRegex(value: string): string {
    return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatTimestamp(value: string | number | Date): string | number | Date {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
}

export function getMimeIcon(mimeType: unknown): string {
    if (!mimeType || typeof mimeType !== 'string') return '📎';
    if (mimeType.startsWith('image/')) return '🖼️';
    if (mimeType.startsWith('audio/')) return '🎵';
    if (mimeType.startsWith('video/')) return '🎬';
    if (mimeType.includes('pdf')) return '📄';
    if (mimeType.includes('zip') || mimeType.includes('gzip')) return '🗜️';
    if (mimeType.startsWith('text/')) return '📄';
    return '📎';
}

/**
 * Preserve message text exactly as-authored, even when link previews exist.
 */
export function getDisplayContent(content: unknown, _linkPreviews?: unknown): string {
    return typeof content === 'string' ? content : '';
}

export function extractBlockRefs(content: string, header: string): BlockRefsResult {
    if (!content) return { content, refs: [] };
    const normalized = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    const lines = normalized.split('\n');
    let start = -1;
    for (let i = 0; i < lines.length; i += 1) {
        if (lines[i].trim() === header && lines[i + 1] && /^\s*-\s+/.test(lines[i + 1])) {
            start = i;
            break;
        }
    }
    if (start === -1) return { content, refs: [] };
    const refs: string[] = [];
    let end = start + 1;
    for (; end < lines.length; end += 1) {
        const line = lines[end];
        if (/^\s*-\s+/.test(line)) {
            refs.push(line.replace(/^\s*-\s+/, '').trim());
        } else {
            break;
        }
    }
    if (refs.length === 0) return { content, refs: [] };
    const before = lines.slice(0, start);
    const after = lines.slice(end);
    let cleaned = [...before, ...after].join('\n');
    cleaned = cleaned.replace(/\n{3,}/g, '\n\n').trim();
    return { content: cleaned, refs };
}

export function extractFileRefs(content: string): { content: string; fileRefs: string[] } {
    const result = extractBlockRefs(content, 'Files:');
    return { content: result.content, fileRefs: result.refs };
}

export function extractMessageRefs(content: string): { content: string; messageRefs: string[] } {
    const result = extractBlockRefs(content, 'Messages:');
    return { content: result.content, messageRefs: result.refs };
}

export function extractAttachmentRefs(content: string): AttachmentRefsResult {
    if (!content) return { content, attachments: [] };
    const normalized = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    const lines = normalized.split('\n');
    let start = -1;
    for (let i = 0; i < lines.length; i += 1) {
        if (lines[i].trim() === 'Images:' && lines[i + 1] && /^\s*-\s+/.test(lines[i + 1])) {
            start = i;
            break;
        }
    }
    if (start === -1) return { content, attachments: [] };
    const refs: AttachmentRef[] = [];
    let end = start + 1;
    for (; end < lines.length; end += 1) {
        const line = lines[end];
        if (/^\s*-\s+/.test(line)) {
            const raw = line.replace(/^\s*-\s+/, '').trim();
            const match = raw.match(/^attachment:([^\s)]+)\s*(?:\((.+)\))?$/i)
                || raw.match(/^attachment:([^\s]+)\s+(.+)$/i);
            if (match) {
                refs.push({ id: match[1], label: (match[2] || '').trim() || match[1], raw });
            } else {
                refs.push({ id: null, label: raw, raw });
            }
        } else if (!line.trim()) {
            break;
        } else {
            break;
        }
    }
    if (refs.length === 0) return { content, attachments: [] };
    const before = lines.slice(0, start);
    const after = lines.slice(end);
    let cleaned = [...before, ...after].join('\n');
    cleaned = cleaned.replace(/\n{3,}/g, '\n\n').trim();
    return { content: cleaned, attachments: refs };
}

export function fallbackAvatarInfo(name: string | null | undefined, avatarUrl: string | null = null): AvatarInfo {
    const label = name || 'Agent';
    const letter = label.charAt(0).toUpperCase() || 'A';
    return { letter, color: '#4ECDC4', image: avatarUrl || null };
}
