import { SessionNameDialog } from './components/session-name-dialog.js';
import { SessionPicker } from './components/session-picker.js';
import { getSessions, getSessionTimeline, createSession, updateSession, deleteSession, getAgentQueue, getSessionModelState } from './api.js';
import { composeDrafts } from './components/compose-drafts.js';
import { eventMatchesSession } from './components/session-events.js';
import { html, render, useState, useEffect, useCallback, useRef, useMemo } from './vendor/preact-htm.js';
import { getTimeline, getPostsByHashtag, searchPosts, getThread, createPost, deletePost, uploadMedia, getThumbnailUrl, getMediaUrl, getMediaInfo, respondToAgentRequest, addToWhitelist, getAgents, getAgentTurnPreview, setAgentTurnPanelExpanded, getWorkspaceFile, updateWorkspaceFile, getAgentContext, getAgentStatus, removeAgentQueueItem, steerAgentQueueItem, reorderAgentQueueItem, SSEClient } from './api.js';
import { ComposeBox } from './components/compose-box.js';
import { Timeline } from './components/timeline.js';
import { AgentStatus, AgentRequestModal, ConnectionStatus } from './components/status.js';
import { WorkspaceExplorer } from './components/workspace-explorer.js';
import { WorkspaceEditor } from './components/editor.js';
import { TerminalPanel } from './components/terminal-panel.js';
import { TabStrip } from './components/tab-strip.js';
import { stashEditorPopoutState, consumeEditorPopoutState } from './panes/editor-popout-transfer.js';
import katex from 'katex';
import { marked } from 'marked';
import { renderMermaid, THEMES as MERMAID_THEMES } from 'beautiful-mermaid';

// URL regex for linkifying text
const URL_REGEX = /(https?:\/\/[^\s<>"{}|\\^`\[\]]+)/g;
// Hashtag regex
const HASHTAG_REGEX = /#(\w+)/g;

// Silence detection thresholds (configurable via window.__VIBES_SILENCE)
function readSilenceOverride(key, fallback) {
    try {
        if (typeof window === 'undefined') return fallback;
        const overrides = window.__VIBES_SILENCE || {};
        const directKey = `__VIBES_SILENCE_${key.toUpperCase()}_MS`;
        const raw = overrides[key] ?? window[directKey];
        const value = Number(raw);
        return Number.isFinite(value) ? value : fallback;
    } catch {
        return fallback;
    }
}

const SILENCE_WARNING_MS = readSilenceOverride('warning', 30_000);
const SILENCE_FINALIZE_MS = readSilenceOverride('finalize', 120_000);
const SILENCE_REFRESH_MS = readSilenceOverride('refresh', 30_000);
const LAST_ACTIVITY_TTL_MS = 30_000;

function buildAgentsMap(data) {
    const map = {};
    (data?.agents || []).forEach((agent) => {
        map[agent.id] = agent;
    });
    return map;
}

function resolveAgentModel(agent) {
    const direct = String(agent?.model || '').trim();
    if (direct) return direct;
    const description = String(agent?.description || '');
    const match = description.match(/\(([^()]+)\)\s*$/);
    const fallback = match?.[1]?.trim() || '';
    return fallback && !/\s/.test(fallback) ? fallback : null;
}

function estimatePreviewLines(text, maxCharsPerLine = 160) {
    const value = String(text || '').replace(/\r\n/g, '\n');
    if (!value) return 0;
    return value
        .split('\n')
        .reduce((acc, line) => acc + Math.max(1, Math.ceil(line.length / maxCharsPerLine)), 0);
}

function getTurnColor(turnId) {
    if (!turnId) return null;
    const palette = [
        '#4ECDC4', '#FF6B6B', '#45B7D1', '#BB8FCE', '#FDCB6E',
        '#00B894', '#74B9FF', '#FD79A8', '#81ECEC', '#FFA07A',
    ];
    const str = String(turnId);
    let hash = 0;
    for (let i = 0; i < str.length; i += 1) {
        hash = (hash * 31 + str.charCodeAt(i)) % 0x7fffffff;
    }
    return palette[Math.abs(hash) % palette.length];
}

function isMarkdownPath(path) {
    return /\.(md|mdx|markdown)$/i.test(String(path || ''));
}

// Configure marked for safe rendering
marked.setOptions({
    breaks: true,  // Convert \n to <br>
    gfm: true,     // GitHub Flavored Markdown
});

/**
 * Decode HTML entities
 */
function decodeEntities(text) {
    if (!text) return text;
    // Escape literal angle brackets so DOMParser doesn't treat them as tags
    const safe = text.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const doc = new DOMParser().parseFromString(safe, 'text/html');
    return doc.documentElement.textContent;
}

function decodeEntitiesDeep(text, maxDepth = 2) {
    if (!text) return text;
    let current = text;
    for (let i = 0; i < maxDepth; i += 1) {
        const next = decodeEntities(current);
        if (next === current) break;
        current = next;
    }
    return current;
}

function extractMermaidBlocks(text) {
    if (!text) return { text: '', blocks: [] };
    const normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    const lines = normalized.split('\n');
    const blocks = [];
    const output = [];
    let inMermaid = false;
    let current = [];

    for (const line of lines) {
        if (!inMermaid && line.trim().match(/^```mermaid\s*$/i)) {
            inMermaid = true;
            current = [];
            continue;
        }
        if (inMermaid && line.trim().match(/^```\s*$/)) {
            const idx = blocks.length;
            blocks.push(current.join('\n'));
            output.push(`@@MERMAID_BLOCK_${idx}@@`);
            inMermaid = false;
            current = [];
            continue;
        }
        if (inMermaid) {
            current.push(line);
        } else {
            output.push(line);
        }
    }

    if (inMermaid) {
        output.push('```mermaid');
        output.push(...current);
    }

    return { text: output.join('\n'), blocks };
}

function decodeMermaidBlock(text) {
    if (!text) return text;
    return decodeEntitiesDeep(text, 5);
}

function injectMermaidBlocks(html, blocks) {
    if (!html || !blocks || blocks.length === 0) return html;
    return html.replace(/@@MERMAID_BLOCK_(\d+)@@/g, (match, idxStr) => {
        const idx = Number(idxStr);
        const raw = blocks[idx] ?? '';
        const decoded = decodeMermaidBlock(raw);
        const encoded = btoa(unescape(encodeURIComponent(decoded)));
        return `<div class="mermaid-container" data-mermaid="${encoded}"><div class="mermaid-loading">Loading diagram...</div></div>`;
    });
}

const ALLOWED_HTML_TAGS = new Set([
    'strong', 'em', 'b', 'i', 'u', 's', 'br', 'p',
    'ul', 'ol', 'li', 'blockquote',
    'ruby', 'rt', 'rp',
]);

function normalizeHtmlCodeTags(text) {
    if (!text) return text;
    return text.replace(/<code>([\s\S]*?)<\/code>/gi, (match, code) => {
        if (code.includes('\n')) {
            return `\n\`\`\`\n${code}\n\`\`\`\n`;
        }
        return `\`${code}\``;
    });
}

function restoreAllowedHtmlTags(text) {
    if (!text) return text;
    return text.replace(/&lt;([\s\S]*?)&gt;/g, (match, content) => {
        const trimmed = content.trim();
        const isClosing = trimmed.startsWith('/');
        const rawTag = isClosing ? trimmed.slice(1).trim() : trimmed;
        const isSelfClosing = rawTag.endsWith('/');
        const tagContent = isSelfClosing ? rawTag.slice(0, -1).trim() : rawTag;
        const tagName = tagContent.split(/\s+/)[0]?.toLowerCase();
        if (!tagName || !ALLOWED_HTML_TAGS.has(tagName)) return match;
        if (tagName === 'br') {
            return isClosing ? '' : '<br>';
        }
        if (isClosing) return `</${tagName}>`;
        return `<${tagName}>`;
    });
}

function decodeCodeEntities(html) {
    if (!html) return html;
    const normalize = (value) => value
        .replace(/&amp;lt;/g, '&lt;')
        .replace(/&amp;gt;/g, '&gt;')
        .replace(/&amp;quot;/g, '&quot;')
        .replace(/&amp;#39;/g, '&#39;')
        .replace(/&amp;amp;/g, '&amp;');
    return html
        .replace(/<pre><code>([\s\S]*?)<\/code><\/pre>/g, (match, code) => `<pre><code>${normalize(code)}</code></pre>`)
        .replace(/<code>([\s\S]*?)<\/code>/g, (match, code) => `<code>${normalize(code)}</code>`);
}

/**
 * Render LaTeX math expressions using KaTeX
 * Handles $$...$$ for display math and $...$ for inline math
 */
function renderMath(html_content) {

    const decodeMath = (value) => decodeEntities(value)
        .replace(/&gt;/g, '>')
        .replace(/&lt;/g, '<')
        .replace(/&amp;/g, '&')
        .replace(/<br\s*\/?\s*>/gi, '\n');

    const escapeHtmlAttr = (value) => String(value || '')
        .replace(/&/g, '&amp;').replace(/"/g, '&quot;')
        .replace(/</g, '&lt;').replace(/>/g, '&gt;');

    // Strip code blocks before math processing to avoid $-in-code false positives
    const codeBlocks = [];
    let stripped = html_content.replace(/<pre\b[^>]*>\s*<code\b[^>]*>[\s\S]*?<\/code>\s*<\/pre>/gi, (m) => {
        codeBlocks.push(m);
        return `@@CODE_BLOCK_${codeBlocks.length - 1}@@`;
    });
    stripped = stripped.replace(/<code\b[^>]*>[\s\S]*?<\/code>/gi, (m) => {
        codeBlocks.push(m);
        return `@@CODE_INLINE_${codeBlocks.length - 1}@@`;
    });

    // Process display math ($$...$$) — require block delimiters on their own line
    stripped = stripped.replace(
        /(^|\n|<br\s*\/?\s*>|<p>|<\/p>)\s*\$\$([\s\S]+?)\$\$\s*(?=\n|<br\s*\/?\s*>|<\/p>|$)/gi,
        (match, leading, tex) => {
            try {
                return `${leading}${katex.renderToString(decodeMath(tex.trim()), { displayMode: true, throwOnError: false })}`;
            } catch (e) {
                return `<span class="math-error" title="${escapeHtmlAttr(e.message)}">${match}</span>`;
            }
        },
    );

    // Process inline math ($...$) — guards against $$, whitespace edges
    stripped = stripped.replace(/(^|[^\\$])\$(?!\s)([^\n$]+?)\$/g, (match, leading, tex) => {
        if (/\s$/.test(tex)) return match;
        try {
            return `${leading}${katex.renderToString(decodeMath(tex), { displayMode: false, throwOnError: false })}`;
        } catch (e) {
            return `${leading}<span class="math-error" title="${escapeHtmlAttr(e.message)}">$${tex}$</span>`;
        }
    });

    // Restore code blocks
    if (codeBlocks.length) {
        stripped = stripped.replace(/@@CODE_(?:BLOCK|INLINE)_(\d+)@@/g, (_m, idx) => codeBlocks[Number(idx)] ?? '');
    }

    return stripped;
}

function normalizeMathFences(text) {
    if (!text) return text;
    const normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    const lines = normalized.split('\n');
    const output = [];
    let inMath = false;

    for (const line of lines) {
        if (!inMath && line.trim().match(/^```(?:math|katex|latex)\s*$/i)) {
            inMath = true;
            output.push('$$');
            continue;
        }
        if (inMath && line.trim().match(/^```\s*$/)) {
            inMath = false;
            output.push('$$');
            continue;
        }
        output.push(line);
    }

    return output.join('\n');
}

function decodeTextEntities(html) {
    if (!html) return html;
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
    const decode = (value) => value
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'")
        .replace(/&amp;/g, '&');
    let node;
    while ((node = walker.nextNode())) {
        if (!node.nodeValue) continue;
        const next = decode(node.nodeValue);
        if (next !== node.nodeValue) {
            node.nodeValue = next;
        }
    }
    return doc.body.innerHTML;
}


/**
 * Render markdown and then linkify hashtags
 */
function renderMarkdown(text, onHashtagClick) {
    if (!text) return '';

    const normalizedMath = normalizeMathFences(text);
    const { text: stripped, blocks: mermaidBlocks } = extractMermaidBlocks(normalizedMath);

    // Decode HTML entities first (in case content has encoded entities)
    const decoded = decodeEntitiesDeep(stripped, 2);
    const normalized = normalizeHtmlCodeTags(decoded);
    const escaped = normalized
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    const safeHtml = restoreAllowedHtmlTags(escaped);

    // Render markdown to HTML (preserve escaped HTML)
    let html_content = marked.parse(safeHtml, { headerIds: false, mangle: false });

    html_content = decodeCodeEntities(html_content);
    html_content = decodeTextEntities(html_content);
    html_content = renderMath(html_content);

    // Process hashtags without breaking links
    html_content = linkifyHashtagsInHtml(html_content);

    // Inject Mermaid blocks after markdown processing to avoid double-encoding
    html_content = injectMermaidBlocks(html_content, mermaidBlocks);

    return html_content;
}

/**
 * Linkify hashtags in rendered HTML, avoiding links/code blocks.
 */
function linkifyHashtagsInHtml(html_content) {
    if (!html_content) return html_content;
    const doc = new DOMParser().parseFromString(html_content, 'text/html');
    const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    let node;
    while ((node = walker.nextNode())) {
        nodes.push(node);
    }
    for (const textNode of nodes) {
        const value = textNode.nodeValue;
        if (!value) continue;
        HASHTAG_REGEX.lastIndex = 0;
        if (!HASHTAG_REGEX.test(value)) continue;
        HASHTAG_REGEX.lastIndex = 0;
        const parent = textNode.parentElement;
        if (parent && (parent.closest('a') || parent.closest('code') || parent.closest('pre'))) continue;
        const parts = value.split(HASHTAG_REGEX);
        if (parts.length <= 1) continue;
        const fragment = doc.createDocumentFragment();
        parts.forEach((part, idx) => {
            if (idx % 2 === 1) {
                const link = doc.createElement('a');
                link.setAttribute('href', '#');
                link.className = 'hashtag';
                link.setAttribute('data-hashtag', part);
                link.textContent = `#${part}`;
                fragment.appendChild(link);
            } else {
                fragment.appendChild(doc.createTextNode(part));
            }
        });
        textNode.parentNode?.replaceChild(fragment, textNode);
    }
    return doc.body.innerHTML;
}

/**
 * Render thinking panels with markdown while keeping tags/quotes intact.
 */
function renderThinkingMarkdown(text) {
    if (!text) return '';
    const normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    const decoded = decodeEntitiesDeep(normalized, 2);
    const normalizedHtml = normalizeHtmlCodeTags(decoded);
    const escaped = normalizedHtml
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    const safeHtml = restoreAllowedHtmlTags(escaped);
    let html_content = marked.parse(safeHtml);
    html_content = decodeCodeEntities(html_content);
    html_content = decodeTextEntities(html_content);
    return html_content;
}

// Render pending mermaid diagrams in the DOM
async function renderMermaidDiagrams(container) {
    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = isDark ? MERMAID_THEMES['tokyo-night'] : MERMAID_THEMES['github-light'];
    
    const pending = container.querySelectorAll('.mermaid-container[data-mermaid]');
    for (const el of pending) {
        try {
            const encoded = el.dataset.mermaid;
            const raw = decodeURIComponent(escape(atob(encoded)));
            const code = decodeEntitiesDeep(raw, 2);
            const svg = await renderMermaid(code, { ...theme, transparent: true });
            el.innerHTML = svg;
            el.removeAttribute('data-mermaid');
        } catch (e) {
            console.error('Mermaid render error:', e);
            el.innerHTML = `<pre class="mermaid-error">Diagram error: ${e.message}</pre>`;
            el.removeAttribute('data-mermaid');
        }
    }
}

/**
 * Linkify text - convert URLs and hashtags to clickable elements (for non-markdown contexts)
 */
function linkifyContent(text, onHashtagClick) {
    if (!text) return text;
    
    // First split by URLs
    const urlParts = text.split(URL_REGEX);
    
    return urlParts.map((part, i) => {
        // Check if this part is a URL
        if (URL_REGEX.test(part)) {
            URL_REGEX.lastIndex = 0;
            return html`<a href=${part} target="_blank" rel="noopener noreferrer" onClick=${(e) => e.stopPropagation()} class="content-link">${part}</a>`;
        }
        
        // Process hashtags in non-URL parts
        const hashtagParts = part.split(HASHTAG_REGEX);
        if (hashtagParts.length === 1) return part;
        
        return hashtagParts.map((hpart, j) => {
            // Every odd index is a captured hashtag (without #)
            if (j % 2 === 1) {
                return html`<a href="#" class="hashtag" onClick=${(e) => { e.preventDefault(); e.stopPropagation(); onHashtagClick?.(hpart); }}>#${hpart}</a>`;
            }
            return hpart;
        });
    });
}

/**
 * Format relative time
 */
function formatTime(timestamp) {
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return timestamp;
    const now = new Date();
    const diffMs = now - date;
    const diffSec = diffMs / 1000;
    const dayMs = 24 * 60 * 60 * 1000;

    if (diffMs < dayMs) {
        if (diffSec < 60) return 'just now';
        if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m`;
        return `${Math.floor(diffSec / 3600)}h`;
    }

    if (diffMs < 5 * dayMs) {
        const weekday = date.toLocaleDateString(undefined, { weekday: 'short' });
        const time = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
        return `${weekday} ${time}`;
    }

    const datePart = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    const timePart = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    return `${datePart} ${timePart}`;
}

/**
 * Format count values for display.
 */
function formatCount(value) {
    if (!Number.isFinite(value)) return '0';
    return Math.round(value).toLocaleString();
}

/**
 * Detect iOS devices for layout adjustments.
 */
function isIOSDevice() {
    if (/iPad|iPhone/.test(navigator.userAgent)) {
        return true;
    }
    // iPadOS Safari (desktop mode) reports as MacIntel with touch points.
    return navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1;
}

/**
 * Hook to force re-render for updating timestamps
 */
function useTimestampRefresh(intervalMs = 30000) {
    const [, setTick] = useState(0);
    
    useEffect(() => {
        const timer = setInterval(() => setTick(t => t + 1), intervalMs);
        return () => clearInterval(timer);
    }, [intervalMs]);
}

const DEFAULT_AGENT_NAME = 'Vibes';
const AGENT_AVATAR_URL = '/static/icon-192.png';

/**
 * Get avatar display info from name and optional image URL.
 * Returns object with { letter, color, image }
 */
function getAvatarInfo(name, avatarUrl = null) {
    const resolvedName = name || DEFAULT_AGENT_NAME;
    const letter = resolvedName.charAt(0).toUpperCase();
    
    // Generate a consistent color based on the letter
    const colors = [
        '#FF6B6B', // red
        '#4ECDC4', // teal
        '#45B7D1', // blue
        '#FFA07A', // light salmon
        '#98D8C8', // mint
        '#F7DC6F', // yellow
        '#BB8FCE', // purple
        '#85C1E2', // sky blue
        '#F8B195', // peach
        '#6C5CE7', // indigo
        '#00B894', // green
        '#FDCB6E', // gold
        '#E17055', // terracotta
        '#74B9FF', // light blue
        '#A29BFE', // lavender
        '#FD79A8', // pink
        '#00CEC9', // cyan
        '#FFEAA7', // light yellow
        '#DFE6E9', // light grey
        '#FF7675', // coral
        '#55EFC4', // aqua
        '#81ECEC', // light cyan
        '#FAB1A0', // salmon
        '#74B9FF', // periwinkle
        '#A29BFE', // soft purple
        '#FD79A8'  // rose
    ];
    
    // Use char code to pick a color consistently
    const index = letter.charCodeAt(0) % colors.length;
    const color = colors[index];

    const normalized = resolvedName.trim().toLowerCase();
    const normalizedAvatar = typeof avatarUrl === 'string' ? avatarUrl.trim() : '';
    const customImage = normalizedAvatar ? normalizedAvatar : null;
    const image = customImage || ((normalized === DEFAULT_AGENT_NAME.toLowerCase() || normalized === 'agent') ? AGENT_AVATAR_URL : null);

    return { letter, color, image };
}

function getAgentName(agentId, agents) {
    if (!agentId) return DEFAULT_AGENT_NAME;
    const name = agents[agentId]?.name || agentId;
    return name ? name.charAt(0).toUpperCase() + name.slice(1) : DEFAULT_AGENT_NAME;
}

function getAgentAvatar(agentId, agents) {
    if (!agentId) return null;
    const agent = agents[agentId] || {};
    return agent.avatar_url || agent.avatarUrl || agent.avatar || null;
}

/**
 * Ensure a <meta> tag exists and return it.
 */
function ensureMetaTag(name) {
    if (typeof document === 'undefined') return null;
    let tag = document.querySelector(`meta[name="${name}"]`);
    if (!tag) {
        tag = document.createElement('meta');
        tag.setAttribute('name', name);
        document.head.appendChild(tag);
    }
    return tag;
}

/**
 * Update browser theme color (affects mobile chrome and PWA title bar)
 */
function updateThemeColor(dark) {
    const color = dark ? '#000000' : '#ffffff';
    const themeMeta = ensureMetaTag('theme-color');
    if (themeMeta) themeMeta.setAttribute('content', color);

    const tileMeta = ensureMetaTag('msapplication-TileColor');
    if (tileMeta) tileMeta.setAttribute('content', color);

    const navMeta = ensureMetaTag('msapplication-navbutton-color');
    if (navMeta) navMeta.setAttribute('content', color);

    const statusMeta = ensureMetaTag('apple-mobile-web-app-status-bar-style');
    if (statusMeta) statusMeta.setAttribute('content', dark ? 'black-translucent' : 'default');
}

/**
 * Apply a UI theme/tint from a ui_theme SSE event or localStorage.
 * Persists to localStorage so it survives page reloads.
 */
function applyUiTheme(data) {
    if (typeof document === 'undefined') return;
    const root = document.documentElement;
    if (data.theme !== undefined) {
        const theme = data.theme || '';
        if (theme && theme !== 'default') {
            root.setAttribute('data-theme', theme);
            localStorage.setItem('vibes-theme', theme);
        } else {
            root.removeAttribute('data-theme');
            localStorage.removeItem('vibes-theme');
        }
    }
    if (data.tint !== undefined) {
        if (data.tint) {
            root.setAttribute('data-tint', data.tint);
            root.style.setProperty('--tint-color', data.tint);
            localStorage.setItem('vibes-tint', data.tint);
        } else {
            root.removeAttribute('data-tint');
            root.style.removeProperty('--tint-color');
            localStorage.removeItem('vibes-tint');
        }
    }
    // Sync browser/PWA title bar colour with the active --bg-primary
    requestAnimationFrame(() => {
        const bg = getComputedStyle(root).getPropertyValue('--bg-primary').trim();
        if (bg) {
            const themeMeta = ensureMetaTag('theme-color');
            if (themeMeta) themeMeta.setAttribute('content', bg);
            const tileMeta = ensureMetaTag('msapplication-TileColor');
            if (tileMeta) tileMeta.setAttribute('content', bg);
            const navMeta = ensureMetaTag('msapplication-navbutton-color');
            if (navMeta) navMeta.setAttribute('content', bg);
        }
    });
}

// Restore theme/tint from localStorage on page load
if (typeof window !== 'undefined') {
    const savedTheme = localStorage.getItem('vibes-theme');
    const savedTint = localStorage.getItem('vibes-tint');
    if (savedTheme) applyUiTheme({ theme: savedTheme });
    if (savedTint) applyUiTheme({ tint: savedTint });
}

const dedupePosts = (items) => {
    const seen = new Set();
    return (items || []).filter((post) => {
        if (!post || seen.has(post.id)) return false;
        seen.add(post.id);
        return true;
    });
};

/**
 * Main App component
 */
function App() {
    const terminalPopout = new URL(location.href).searchParams.get('terminal') === '1';
    const [terminalVisible, setTerminalVisible] = useState(terminalPopout);
    const [terminalEnabled, setTerminalEnabled] = useState(false);
    useEffect(() => {
        fetch('/terminal/session').then(r => r.json()).then(s => setTerminalEnabled(!!s.enabled)).catch(() => {});
    }, []);
    const [posts, setPosts] = useState(null);
    const [selectedSession, setSelectedSession] = useState('default');
    const selectedSessionRef = useRef('default');
    const switchGeneration = useRef(0);
    const searchGeneration = useRef(0);
    const modelGeneration = useRef(0);
    const [sessionOptions, setSessionOptions] = useState([]);
    const [sessionPickerOpen, setSessionPickerOpen] = useState(false);
    const [renamingSession, setRenamingSession] = useState(null);
    const [creatingSession, setCreatingSession] = useState(false);
    const createdSessionRef = useRef(null);
    const refreshSessions = async () => {
        const result = await getSessions(true);
        setSessionOptions(result.sessions);
    };
    useEffect(() => {
        if (!sessionPickerOpen) return;
        let disposed = false;
        let loading = false;
        const refresh = async () => {
            if (loading) return;
            loading = true;
            try {
                const result = await getSessions(true);
                if (!disposed) setSessionOptions(result.sessions);
            } catch (error) { console.warn('Session picker refresh failed:', error); }
            finally { loading = false; }
        };
        const timer = window.setInterval(refresh, 3000);
        return () => { disposed = true; window.clearInterval(timer); };
    }, [sessionPickerOpen]);
    const selectSession = async (id) => {
        const generation = ++switchGeneration.current;
        const result = await getSessionTimeline(id);
        if (generation !== switchGeneration.current) return;
        const draft = composeDrafts.load(id);
        searchGeneration.current++;
        selectedSessionRef.current = id;
        setSelectedSession(id);
        setPosts(result.posts);
        setHasMore(result.has_more);
        setFileRefs(draft.fileRefs); setFolderRefs(draft.folderRefs); setMessageRefs(draft.messageRefs);
        setCurrentHashtag(null); setSearchQuery(null); setSearchOpen(false);
        setAgentStatus(null); setAgentDraft(null); setAgentPlan(null); setAgentThought(null);
        setContextUsage(null); setActiveModel(null); setActiveThinkingLevel(null);
        setQueuedFollowups([]); setPendingRequest(null);
        clearAgentRunState();
        setSessionPickerOpen(false);
    };
    const [hasMore, setHasMore] = useState(false);
    const [connectionStatus, setConnectionStatus] = useState('disconnected');
    const [currentHashtag, setCurrentHashtag] = useState(null);
    const [searchQuery, setSearchQuery] = useState(null);
    const [searchOpen, setSearchOpen] = useState(false);
    const [fileRefs, setFileRefs] = useState(() => composeDrafts.load('default').fileRefs);
    const [folderRefs, setFolderRefs] = useState(() => composeDrafts.load('default').folderRefs);
    const [messageRefs, setMessageRefs] = useState(() => composeDrafts.load('default').messageRefs);
    const [agentStatus, setAgentStatus] = useState(null);
    const [agentDraft, setAgentDraft] = useState({ text: '', totalLines: 0 });
    const [agentPlan, setAgentPlan] = useState('');
    const [agentThought, setAgentThought] = useState({ text: '', totalLines: 0 });
    const [pendingRequest, setPendingRequest] = useState(null);
    const [currentTurnId, setCurrentTurnId] = useState(null);
    const [steerQueuedTurnId, setSteerQueuedTurnId] = useState(null);
    const [queuedFollowups, setQueuedFollowups] = useState([]);
    const [agents, setAgents] = useState({});
    const [activeModel, setActiveModel] = useState(null);
    const [activeThinkingLevel, setActiveThinkingLevel] = useState(null);
    const [supportsThinking, setSupportsThinking] = useState(false);
    const [contextUsage, setContextUsage] = useState(null);
    const [notificationsEnabled, setNotificationsEnabled] = useState(false);
    const [notificationPermission, setNotificationPermission] = useState('default');
    const [removingPostIds, setRemovingPostIds] = useState(() => new Set());
    const [workspaceOpen, setWorkspaceOpen] = useState(() => {
        if (typeof window === 'undefined') return true;
        if (new URLSearchParams(window.location.search).has('popout')) return false;
        const stored = localStorage.getItem('workspaceOpen');
        return stored === null ? true : stored === 'true';
    });
    const [popoutMode] = useState(() => {
        if (typeof window === 'undefined') return false;
        return new URLSearchParams(window.location.search).has('popout');
    });
    const [editorTabs, setEditorTabs] = useState([]);
    const [activeEditorTabId, setActiveEditorTabId] = useState(null);
    const [previewTabs, setPreviewTabs] = useState(() => new Set());
    const [userProfile, setUserProfile] = useState({ name: 'You', avatar_url: null, avatar_background: null });
    const hasConnectedOnceRef = useRef(false);
    const wasAgentActiveRef = useRef(false);
    const agentsRef = useRef({});
    const viewStateRef = useRef({ currentHashtag: null, searchQuery: null });
    const hasMoreRef = useRef(false);
    const loadMoreRef = useRef(null);
    const timelineRef = useRef(null);
    const lastAgentEventRef = useRef(null);
    const lastSilenceNoticeRef = useRef(0);
    const isAgentRunningRef = useRef(false);
    const draftBufferRef = useRef('');
    const thoughtBufferRef = useRef('');
    const expandedPanelsRef = useRef({ draft: false, thought: false });
    const pendingRequestRef = useRef(null);
    const stalledPostIdRef = useRef(null);
    const currentTurnIdRef = useRef(null);
    const steerQueuedTurnIdRef = useRef(null);
    const notificationsEnabledRef = useRef(false);
    const lastNotifiedIdRef = useRef(null);
    const lastAgentResponseRef = useRef(null);
    const lastActivityTimerRef = useRef(null);
    const lastActivityTokenRef = useRef(0);
    const appShellRef = useRef(null);
    const sidebarWidthRef = useRef(0);
    const editorWidthRef = useRef(0);
    const brandingRef = useRef({ title: null, avatarBase: null });
    
    // Refresh timestamps every 30 seconds
    useTimestampRefresh(30000);

    const refreshSelectedContext = async () => {
        const session = selectedSessionRef.current;
        const generation = switchGeneration.current;
        try {
            const context = await getAgentContext(session);
            if (session === selectedSessionRef.current && generation === switchGeneration.current) {
                setContextUsage(context?.percent != null ? context : null);
            }
        } catch {
            if (session === selectedSessionRef.current && generation === switchGeneration.current) setContextUsage(null);
        }
    };
    useEffect(() => {
        refreshSelectedContext();
        let disposed = false;
        const refreshModel = async () => {
            const generation = modelGeneration.current;
            try {
                const state = await getSessionModelState(selectedSession);
                if (disposed || selectedSession !== selectedSessionRef.current || generation !== modelGeneration.current) return;
                const model = state.available ? state.model : null;
                setActiveModel(model ? [model.provider, model.id || model.name].filter(Boolean).join('/') : null);
                setActiveThinkingLevel(state.available ? state.thinking_level : null);
                setSupportsThinking(model?.reasoning === true);
            } catch {
                if (!disposed && selectedSession === selectedSessionRef.current && generation === modelGeneration.current) {
                    setActiveModel(null); setActiveThinkingLevel(null); setSupportsThinking(false);
                }
            }
        };
        refreshModel();
        const timer = setInterval(refreshModel, 15000);
        return () => { disposed = true; clearInterval(timer); };
    }, [selectedSession]);
    const refreshSelectedQueue = async () => {
        const session = selectedSessionRef.current;
        const result = await getAgentQueue(null, null, session);
        if (session === selectedSessionRef.current) setQueuedFollowups(result.items || []);
    };
    useEffect(() => {
        let disposed = false;
        const refresh = async () => {
            try {
                const result = await getAgentQueue(null, null, selectedSession);
                if (!disposed) setQueuedFollowups(result.items || []);
            } catch (error) { console.warn('Queue refresh failed:', error); }
        };
        refresh();
        const timer = setInterval(refresh, 3000);
        return () => { disposed = true; clearInterval(timer); };
    }, [selectedSession]);
    useEffect(() => {
        let disposed = false;
        getAgentStatus(selectedSession).then(status => {
            if (disposed || selectedSessionRef.current !== selectedSession) return;
            const turns = status.active_turns || [];
            if (turns.length) {
                const turn = turns[turns.length - 1];
                setActiveTurn(turn.turn_id);
                isAgentRunningRef.current = true;
                setAgentStatus({ ...(turn.last_status || { type: 'thinking', title: 'Thinking...' }), turn_id: turn.turn_id, thread_id: turn.thread_id });
            }
        }).catch(error => console.warn('Session status refresh failed:', error));
        return () => { disposed = true; };
    }, [selectedSession]);
    const syncQueueState = useCallback((statusData) => {
        if (!statusData) return;
        refreshSelectedQueue().catch(error => console.warn('Queue refresh failed:', error));
        const pendingSteers = Array.isArray(statusData.pending_steers) ? statusData.pending_steers : [];
        const turns = Array.isArray(statusData.active_turns) ? statusData.active_turns : [];
        if (pendingSteers.length > 0 && turns.length > 0) {
            const activeTurnId = turns[turns.length - 1]?.turn_id || null;
            steerQueuedTurnIdRef.current = activeTurnId;
            setSteerQueuedTurnId(activeTurnId);
        } else if (pendingSteers.length === 0 && !isAgentRunningRef.current) {
            steerQueuedTurnIdRef.current = null;
            setSteerQueuedTurnId(null);
        }
    }, []);

    const applyBranding = useCallback((name, avatarUrl, avatarVersion = null) => {
        if (typeof document === 'undefined') return;
        const title = (name || '').trim() || 'Vibes';
        if (brandingRef.current.title !== title) {
            document.title = title;
            const titleMeta = document.querySelector('meta[name="apple-mobile-web-app-title"]');
            if (titleMeta && titleMeta.getAttribute('content') !== title) {
                titleMeta.setAttribute('content', title);
            }
            brandingRef.current.title = title;
        }
        const favicon = document.getElementById('dynamic-favicon');
        if (!favicon) return;
        const defaultHref = favicon.getAttribute('data-default') || favicon.getAttribute('href') || '/favicon.ico';
        const baseHref = avatarUrl || defaultHref;
        const avatarKey = avatarUrl ? `${baseHref}|${avatarVersion || ''}` : baseHref;
        if (brandingRef.current.avatarBase !== avatarKey) {
            const cacheBust = avatarUrl ? `${baseHref}${baseHref.includes('?') ? '&' : '?'}v=${avatarVersion || Date.now()}` : baseHref;
            favicon.setAttribute('href', cacheBust);
            brandingRef.current.avatarBase = avatarKey;
        }
    }, []);

    useEffect(() => {
        if (typeof window === 'undefined') return;
        const stored = localStorage.getItem('notificationsEnabled');
        const enabled = stored === 'true';
        notificationsEnabledRef.current = enabled;
        setNotificationsEnabled(enabled);
        if (typeof Notification !== 'undefined') {
            setNotificationPermission(Notification.permission);
        }
    }, []);

    useEffect(() => {
        notificationsEnabledRef.current = notificationsEnabled;
    }, [notificationsEnabled]);

    useEffect(() => {
        if (typeof window === 'undefined') return;
        localStorage.setItem('workspaceOpen', String(workspaceOpen));
    }, [workspaceOpen]);

    const toggleWorkspace = useCallback(() => {
        setWorkspaceOpen((prev) => !prev);
    }, []);

    const openEditor = useCallback(async (path) => {
        if (!path) return;
        if (editorTabs.some((tab) => tab.id === path)) {
            setActiveEditorTabId(path);
            return;
        }
        setActiveEditorTabId(path);
        setEditorTabs((prev) => {
            if (prev.some((tab) => tab.id === path)) return prev;
            return [...prev, {
                id: path,
                path,
                label: path.split('/').pop() || path,
                content: '',
                savedContent: '',
                loading: true,
                error: null,
                dirty: false,
                pinned: false,
                saving: false,
                saveError: null,
                savedAt: null,
                isMarkdown: isMarkdownPath(path),
            }];
        });
        try {
            const data = await getWorkspaceFile(path, 5_000_000, 'edit');
            if (data?.kind === 'text') {
                setEditorTabs((prev) => prev.map((tab) => (
                    tab.id === path
                        ? {
                            ...tab,
                            content: data.text || '',
                            savedContent: data.text || '',
                            loading: false,
                            error: null,
                            dirty: false,
                            saveError: null,
                        }
                        : tab
                )));
            } else {
                setEditorTabs((prev) => prev.map((tab) => (
                    tab.id === path ? { ...tab, content: '', savedContent: '', loading: false, error: 'File is not a text file' } : tab
                )));
            }
        } catch (err) {
            setEditorTabs((prev) => prev.map((tab) => (
                tab.id === path ? { ...tab, content: '', savedContent: '', loading: false, error: err?.message || 'Failed to load file' } : tab
            )));
        }
    }, [editorTabs]);

    const closeEditorTab = useCallback((tabId) => {
        if (!tabId) return;
        const tabs = editorTabs;
        const target = tabs.find((tab) => tab.id === tabId);
        if (!target) return;
        if (target.dirty && !window.confirm(`"${target.label}" has unsaved changes. Close anyway?`)) {
            return;
        }
        const idx = tabs.findIndex((tab) => tab.id === tabId);
        const remaining = tabs.filter((tab) => tab.id !== tabId);
        setEditorTabs(remaining);
        setPreviewTabs((prev) => {
            if (!prev.has(tabId)) return prev;
            const next = new Set(prev);
            next.delete(tabId);
            return next;
        });
        if (activeEditorTabId === tabId) {
            const fallback = remaining[Math.max(0, idx - 1)] || remaining[idx] || remaining[remaining.length - 1] || null;
            setActiveEditorTabId(fallback?.id || null);
        }
    }, [activeEditorTabId, editorTabs]);

    const closeEditor = useCallback(() => {
        closeEditorTab(activeEditorTabId);
    }, [activeEditorTabId, closeEditorTab]);

    const handleEditorSave = useCallback(async (content) => {
        const path = activeEditorTabId;
        if (!path) return;
        setEditorTabs((prev) => prev.map((tab) => (
            tab.id === path ? { ...tab, saving: true, saveError: null } : tab
        )));
        try {
            await updateWorkspaceFile(path, content);
            const savedAt = Date.now();
            setEditorTabs((prev) => prev.map((tab) => (
                tab.id === path
                    ? { ...tab, content, savedContent: content, dirty: false, saving: false, saveError: null, savedAt }
                    : tab
            )));
        } catch (err) {
            setEditorTabs((prev) => prev.map((tab) => (
                tab.id === path ? { ...tab, saving: false, saveError: err?.message || 'Save failed' } : tab
            )));
        }
    }, [activeEditorTabId]);

    const handleEditorChange = useCallback((nextContent, nextDirty) => {
        const path = activeEditorTabId;
        if (!path) return;
        setEditorTabs((prev) => prev.map((tab) => (
            tab.id === path ? { ...tab, content: nextContent, dirty: Boolean(nextDirty), saveError: null } : tab
        )));
    }, [activeEditorTabId]);

    const handleTabActivate = useCallback((tabId) => {
        setActiveEditorTabId(tabId);
    }, []);

    const handleTabCloseOthers = useCallback((keepId) => {
        const closable = editorTabs.filter((tab) => tab.id !== keepId && !tab.pinned);
        const dirtyCount = closable.filter((tab) => tab.dirty).length;
        if (dirtyCount > 0 && !window.confirm(`${dirtyCount} unsaved tab${dirtyCount > 1 ? 's' : ''} will be closed. Continue?`)) {
            return;
        }
        const nextTabs = editorTabs.filter((tab) => tab.id === keepId || tab.pinned);
        setEditorTabs(nextTabs);
        setPreviewTabs((prev) => {
            const next = new Set(prev);
            closable.forEach((tab) => next.delete(tab.id));
            return next;
        });
        setActiveEditorTabId(keepId);
    }, [editorTabs]);

    const handleTabCloseAll = useCallback(() => {
        const closable = editorTabs.filter((tab) => !tab.pinned);
        const dirtyCount = closable.filter((tab) => tab.dirty).length;
        if (dirtyCount > 0 && !window.confirm(`${dirtyCount} unsaved tab${dirtyCount > 1 ? 's' : ''} will be closed. Continue?`)) {
            return;
        }
        const nextTabs = editorTabs.filter((tab) => tab.pinned);
        setEditorTabs(nextTabs);
        setPreviewTabs((prev) => {
            const next = new Set(prev);
            closable.forEach((tab) => next.delete(tab.id));
            return next;
        });
        setActiveEditorTabId(nextTabs[0]?.id || null);
    }, [editorTabs]);

    const handleTabTogglePin = useCallback((tabId) => {
        setEditorTabs((prev) => prev.map((tab) => (
            tab.id === tabId ? { ...tab, pinned: !tab.pinned } : tab
        )));
    }, []);

    const handleTabTogglePreview = useCallback((tabId) => {
        if (!tabId) return;
        setPreviewTabs((prev) => {
            const next = new Set(prev);
            if (next.has(tabId)) next.delete(tabId);
            else next.add(tabId);
            return next;
        });
    }, []);

    const handlePopOutTab = useCallback((tabId, label) => {
        if (!tabId) return;
        const tab = editorTabs.find((t) => t.id === tabId);
        const transferPayload = stashEditorPopoutState({
            path: tabId,
            content: tab?.content,
            savedContent: tab?.savedContent,
            mtime: tab?.savedAt ? new Date(tab.savedAt).toISOString() : null,
        });
        const params = new URLSearchParams();
        params.set('editor', tabId);
        params.set('popout', '1');
        if (transferPayload?.editor_popout) {
            params.set('editor_popout', transferPayload.editor_popout);
        }
        const url = `${window.location.origin}${window.location.pathname}?${params}`;
        // Explicit left/top + toolbar=no forces a real window in Safari
        // (Safari ignores the `popup` keyword and opens a tab otherwise)
        const w = 820, h = 620;
        const left = Math.round((screen.width - w) / 2);
        const top = Math.round((screen.height - h) / 2);
        const popup = window.open(url, `vibes-editor-${tabId}`,
            `width=${w},height=${h},left=${left},top=${top},toolbar=no,menubar=no,location=no,status=no`);
        // Popup blockers must never discard the only visible copy of an editor.
        if (!popup) return;
        // Remove the tab from this window
        setEditorTabs((prev) => prev.filter((t) => t.id !== tabId));
        setActiveEditorTabId((prev) => {
            if (prev !== tabId) return prev;
            const remaining = editorTabs.filter((t) => t.id !== tabId);
            return remaining[remaining.length - 1]?.id || null;
        });
    }, [editorTabs]);

    // Open editor from URL params on startup (?editor=path, optional ?popout=1)
    useEffect(() => {
        const url = new URL(window.location.href);
        const editorPath = url.searchParams.get('editor')?.trim();
        const popoutToken = url.searchParams.get('editor_popout')?.trim();

        if (!editorPath) return;

        // Clean the URL params so a refresh doesn't re-trigger
        url.searchParams.delete('editor');
        url.searchParams.delete('editor_popout');
        url.searchParams.delete('popout');
        window.history.replaceState(window.history.state, document.title, url.toString());

        // Try to consume stashed editor state (content + cursor)
        const transferred = popoutToken
            ? consumeEditorPopoutState(popoutToken)
            : null;

        if (transferred?.content !== undefined) {
            // Hydrate the tab directly from transferred state (skips fetch)
            setEditorTabs((prev) => {
                if (prev.some((tab) => tab.id === editorPath)) return prev;
                return [...prev, {
                    id: editorPath,
                    path: editorPath,
                    label: editorPath.split('/').pop() || editorPath,
                    content: transferred.content,
                    savedContent: transferred.savedContent ?? transferred.content,
                    loading: false,
                    error: null,
                    dirty: transferred.savedContent !== undefined && transferred.savedContent !== transferred.content,
                    pinned: false,
                    saving: false,
                    saveError: null,
                    savedAt: null,
                    isMarkdown: isMarkdownPath(editorPath),
                }];
            });
            setActiveEditorTabId(editorPath);
        } else {
            openEditor(editorPath);
        }
    }, []);

    useEffect(() => {
        const hasUnsaved = editorTabs.some((tab) => tab.dirty);
        const onBeforeUnload = (event) => {
            if (!hasUnsaved) return;
            event.preventDefault();
            event.returnValue = '';
        };
        window.addEventListener('beforeunload', onBeforeUnload);
        return () => window.removeEventListener('beforeunload', onBeforeUnload);
    }, [editorTabs]);

    const addFileRef = useCallback((path) => {
        if (!path) return;
        setFileRefs((prev) => (prev.includes(path) ? prev : [...prev, path]));
    }, []);

    const removeFileRef = useCallback((path) => {
        setFileRefs((prev) => prev.filter((item) => item !== path));
    }, []);

    const clearFileRefs = useCallback(() => {
        setFileRefs([]);
    }, []);

    const addMessageRef = useCallback((id) => {
        if (!id) return;
        setMessageRefs((prev) => (prev.includes(id) ? prev : [...prev, id]));
    }, []);

    const removeMessageRef = useCallback((id) => {
        setMessageRefs((prev) => prev.filter((item) => item !== id));
    }, []);

    const clearMessageRefs = useCallback(() => {
        setMessageRefs([]);
    }, []);

    const scrollToMessage = useCallback(async (id) => {
        const highlight = (el) => {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            el.classList.add('post-highlight');
            setTimeout(() => el.classList.remove('post-highlight'), 2000);
        };
        const existing = document.getElementById('post-' + id);
        if (existing) { highlight(existing); return; }
        try {
            const result = await api.getThread(id);
            const msg = result?.thread?.[0];
            if (!msg) return;
            setPosts((prev) => {
                if (!prev) return [msg];
                if (prev.some((p) => p.id === msg.id)) return prev;
                return [...prev, msg];
            });
            requestAnimationFrame(() => {
                setTimeout(() => {
                    const el = document.getElementById('post-' + id);
                    if (el) highlight(el);
                }, 50);
            });
        } catch (err) {
            console.error('[scrollToMessage] Failed to fetch message', id, err);
        }
    }, []);

    const noteAgentActivity = useCallback((options = {}) => {
        lastAgentEventRef.current = Date.now();
        if (options.running) {
            isAgentRunningRef.current = true;
        }
        if (options.clearSilence) {
            lastSilenceNoticeRef.current = 0;
        }
    }, []);

    const updateAgentProfile = useCallback((payload) => {
        if (!payload || typeof payload !== 'object') return;
        const agentId = payload.agent_id;
        if (!agentId) return;
        const nextName = payload.agent_name;
        const nextAvatar = payload.agent_avatar;
        if (!nextName && nextAvatar === undefined) return;

        const current = agentsRef.current?.[agentId] || { id: agentId };
        let resolvedName = current.name || null;
        let resolvedAvatar = current.avatar_url ?? current.avatarUrl ?? current.avatar ?? null;
        let avatarChanged = false;
        let nameChanged = false;

        if (nextName && nextName !== current.name) {
            resolvedName = nextName;
            nameChanged = true;
        }

        if (nextAvatar !== undefined) {
            const normalizedAvatar = typeof nextAvatar === 'string' ? nextAvatar.trim() : null;
            const normalizedCurrent = typeof resolvedAvatar === 'string' ? resolvedAvatar.trim() : null;
            const nextValue = normalizedAvatar || null;
            const currentValue = normalizedCurrent || null;
            if (nextValue !== currentValue) {
                resolvedAvatar = nextValue;
                avatarChanged = true;
            }
        }

        if (!nameChanged && !avatarChanged) return;

        setAgents((prev) => {
            const currentEntry = prev[agentId] || { id: agentId };
            const updated = { ...currentEntry };
            if (nameChanged) updated.name = resolvedName;
            if (avatarChanged) updated.avatar_url = resolvedAvatar;
            return { ...prev, [agentId]: updated };
        });

        if (agentId === 'default') {
            applyBranding(resolvedName, resolvedAvatar, avatarChanged ? Date.now() : null);
        }
    }, [applyBranding]);

    const updateUserProfile = useCallback((payload) => {
        if (!payload || typeof payload !== 'object') return;
        const nextName = payload.user_name ?? payload.userName;
        const nextAvatar = payload.user_avatar ?? payload.userAvatar;
        const nextBg = payload.user_avatar_background ?? payload.userAvatarBackground;
        if (nextName === undefined && nextAvatar === undefined && nextBg === undefined) return;
        setUserProfile((prev) => {
            const resolvedName = typeof nextName === 'string' && nextName.trim() ? nextName.trim() : prev.name || 'You';
            const resolvedAvatar = nextAvatar === undefined ? prev.avatar_url
                : (typeof nextAvatar === 'string' && nextAvatar.trim() ? nextAvatar.trim() : null);
            const resolvedBg = nextBg === undefined ? prev.avatar_background
                : (typeof nextBg === 'string' && nextBg.trim() ? nextBg.trim() : null);
            if (prev.name === resolvedName && prev.avatar_url === resolvedAvatar && prev.avatar_background === resolvedBg) return prev;
            return { name: resolvedName, avatar_url: resolvedAvatar, avatar_background: resolvedBg };
        });
    }, []);

    useEffect(() => {
        agentsRef.current = agents;
    }, [agents]);

    useEffect(() => {
        if (!posts || posts.length === 0) return;
        const hash = location.hash;
        if (!hash || !hash.startsWith('#msg-')) return;
        const msgId = hash.slice(5);
        scrollToMessage(msgId);
        history.replaceState(null, '', location.pathname + location.search);
    }, [posts, scrollToMessage]);

    const handleToggleNotifications = useCallback(async () => {
        if (typeof window === 'undefined' || typeof Notification === 'undefined') return;
        if (!window.isSecureContext) {
            alert('Notifications require a secure context (HTTPS or installed app).');
            return;
        }
        if (Notification.permission === 'denied') {
            setNotificationPermission('denied');
            alert('Browser notifications are blocked. Enable them in your browser settings.');
            return;
        }
        if (Notification.permission === 'default') {
            const result = await (typeof Notification.requestPermission === 'function'
                ? Notification.requestPermission()
                : Promise.resolve('default'));
            setNotificationPermission(result || 'default');
            if (result !== 'granted') {
                notificationsEnabledRef.current = false;
                setNotificationsEnabled(false);
                localStorage.setItem('notificationsEnabled', 'false');
                return;
            }
        }
        const next = !notificationsEnabledRef.current;
        notificationsEnabledRef.current = next;
        setNotificationsEnabled(next);
        localStorage.setItem('notificationsEnabled', String(next));
    }, []);

    const notifyForFinalResponse = useCallback(() => {
        if (!notificationsEnabledRef.current) return;
        if (typeof Notification === 'undefined') return;
        if (Notification.permission !== 'granted') return;
        if (typeof document !== 'undefined') {
            const hasFocus = typeof document.hasFocus === 'function' ? document.hasFocus() : true;
            if (!document.hidden && hasFocus) return;
        }
        const entry = lastAgentResponseRef.current;
        if (!entry || !entry.post) return;
        const post = entry.post;
        if (post.id && lastNotifiedIdRef.current === post.id) return;
        const content = String(post?.data?.content || '').trim();
        if (!content) return;
        lastNotifiedIdRef.current = post.id || lastNotifiedIdRef.current;
        lastAgentResponseRef.current = null;
        const body = content.replace(/\s+/g, ' ').slice(0, 200);
        const agentsMap = agentsRef.current || {};
        const agent = post?.data?.agent_id ? agentsMap[post.data.agent_id] : null;
        const title = agent?.name || 'Agent';
        try {
            const notification = new Notification(title, { body });
            notification.onclick = () => { try { window.focus(); } catch { /* ignore */ } };
        } catch { /* ignore */ }
    }, []);

    const clearAgentRunState = useCallback(() => {
        isAgentRunningRef.current = false;
        lastAgentEventRef.current = null;
        lastSilenceNoticeRef.current = 0;
        draftBufferRef.current = '';
        thoughtBufferRef.current = '';
        expandedPanelsRef.current = { draft: false, thought: false };
        pendingRequestRef.current = null;
        currentTurnIdRef.current = null;
        steerQueuedTurnIdRef.current = null;
        setCurrentTurnId(null);
        setSteerQueuedTurnId(null);

        // Show "Last activity" briefly then auto-clear
        if (lastActivityTimerRef.current) {
            clearTimeout(lastActivityTimerRef.current);
            lastActivityTimerRef.current = null;
        }
        lastActivityTokenRef.current = 0;
        setAgentStatus((prev) => {
            if (!prev) return prev;
            if (!(prev.last_activity || prev.lastActivity)) return prev;
            const { last_activity, lastActivity, ...rest } = prev;
            return Object.keys(rest).length ? rest : null;
        });
        const token = Date.now();
        lastActivityTokenRef.current = token;
        setAgentStatus((prev) => {
            if (prev && prev.type && prev.type !== 'done' && prev.type !== 'error' && prev.type !== 'cancelled') return prev;
            return { type: 'last_activity', last_activity: true, title: 'Last activity just now' };
        });
        lastActivityTimerRef.current = setTimeout(() => {
            if (lastActivityTokenRef.current !== token) return;
            setAgentStatus((prev) => {
                if (!prev || !(prev.last_activity || prev.lastActivity)) return prev;
                return null;
            });
            lastActivityTimerRef.current = null;
        }, LAST_ACTIVITY_TTL_MS);
    }, [setCurrentTurnId, setSteerQueuedTurnId]);

    const setActiveTurn = useCallback((turnId) => {
        if (!turnId) return;
        if (currentTurnIdRef.current === turnId) return;
        currentTurnIdRef.current = turnId;
        setCurrentTurnId(turnId);
        draftBufferRef.current = '';
        thoughtBufferRef.current = '';
        expandedPanelsRef.current = { draft: false, thought: false };
        setAgentDraft({ text: '', totalLines: 0 });
        setAgentPlan('');
        setAgentThought({ text: '', totalLines: 0 });
        setPendingRequest(null);
        pendingRequestRef.current = null;
    }, [setCurrentTurnId]);

    const removeStalledPost = useCallback(() => {
        const stalledId = stalledPostIdRef.current;
        if (!stalledId) return;
        setPosts((prev) => (prev ? prev.filter((post) => post.id !== stalledId) : prev));
        stalledPostIdRef.current = null;
    }, []);

    useEffect(() => {
        viewStateRef.current = { currentHashtag, searchQuery };
    }, [currentHashtag, searchQuery]);

    useEffect(() => {
        hasMoreRef.current = hasMore;
    }, [hasMore]);

    // Scroll to bottom of timeline (column-reverse: bottom is scrollTop=0)
    const scrollToBottomRef = useRef(null);
    const scrollToBottom = useCallback(() => {
        if (timelineRef.current) {
            timelineRef.current.scrollTop = 0;
        }
    }, []);
    scrollToBottomRef.current = scrollToBottom;

    const finalizeStalledResponse = useCallback(() => {
        if (!isAgentRunningRef.current) return;
        isAgentRunningRef.current = false;
        lastSilenceNoticeRef.current = 0;
        lastAgentEventRef.current = null;
        currentTurnIdRef.current = null;
        setCurrentTurnId(null);

        const partial = (draftBufferRef.current || '').trim();
        draftBufferRef.current = '';
        thoughtBufferRef.current = '';
        expandedPanelsRef.current = { draft: false, thought: false };
        setAgentDraft({ text: '', totalLines: 0 });
        setAgentPlan('');
        setAgentThought({ text: '', totalLines: 0 });
        setPendingRequest(null);
        pendingRequestRef.current = null;

        if (!partial) {
            setAgentStatus({ type: 'error', title: 'Response stalled — No content received' });
            return;
        }

        const warning = '\n\n⚠️ Response may be incomplete — the model stopped responding';
        const content = `${partial}${warning}`;
        const id = Date.now();
        const timestamp = new Date().toISOString();
        const localPost = {
            id,
            timestamp,
            data: {
                type: 'agent_response',
                content,
                agent_id: 'default',
                is_local_stall: true,
            },
        };

        stalledPostIdRef.current = id;
        setPosts((prev) => (prev ? dedupePosts([...prev, localPost]) : [localPost]));
        scrollToBottomRef.current?.();
        setAgentStatus(null);
    }, [setCurrentTurnId]);
    
    // Load timeline or hashtag posts
    const loadPosts = useCallback(async (hashtag = null) => {
        try {
            if (hashtag) {
                const result = await getPostsByHashtag(hashtag);
                setPosts(result.posts);
                setHasMore(false);
            } else {
                const session = selectedSessionRef.current;
                const result = await getTimeline(10, null, session);
                if (session !== selectedSessionRef.current) return;
                setPosts(result.posts);
                setHasMore(result.has_more);
            }
        } catch (error) {
            console.error('Failed to load posts:', error);
        }
    }, []);

    const handleConnectionStatusChange = useCallback((status) => {
        setConnectionStatus(status);
        if (status !== 'connected') {
            setAgentStatus(null);
            setAgentDraft({ text: '', totalLines: 0 });
            setAgentPlan('');
            setAgentThought({ text: '', totalLines: 0 });
            setPendingRequest(null);
            pendingRequestRef.current = null;
            clearAgentRunState();
            return;
        }
        if (!hasConnectedOnceRef.current) {
            hasConnectedOnceRef.current = true;
        }
        // On every (re)connect, poll agent status to restore in-flight state
        const statusSession = selectedSessionRef.current;
        getAgentStatus(statusSession).then((statusData) => {
            if (!statusData || statusSession !== selectedSessionRef.current) return;
            syncQueueState(statusData);
            const turns = statusData.active_turns || [];
            if (turns.length > 0) {
                const turn = turns[turns.length - 1];
                setActiveTurn(turn.turn_id);
                noteAgentActivity({ running: true, clearSilence: true });
                const lastStatus = turn.last_status || { type: 'thinking', title: 'Thinking...' };
                setAgentStatus({
                    thread_id: turn.thread_id,
                    agent_id: turn.agent_id,
                    turn_id: turn.turn_id,
                    ...lastStatus,
                });
            }
        }).catch(() => {});
        // Always refresh context usage on reconnect
        getAgentContext().then(ctx => {
            if (ctx && ctx.percent != null) setContextUsage(selectedSessionRef.current === 'default' ? ctx : null);
        }).catch(() => {});
        const { currentHashtag: activeHashtag, searchQuery: activeSearch } = viewStateRef.current;
        if (!activeHashtag && !activeSearch) {
            loadPosts();
        }
    }, [clearAgentRunState, loadPosts, setActiveTurn, noteAgentActivity, syncQueueState]);
    
    // Load older messages (prepend)
    const loadMore = useCallback(async () => {
        if (!posts || posts.length === 0) return;
        
        // Find oldest post id
        const sortedPosts = posts.slice().sort((a, b) => a.id - b.id);
        const oldestId = sortedPosts[0].id;
        
        console.log('Loading more before id:', oldestId);
        try {
            const session = selectedSessionRef.current;
            const result = await getTimeline(5, oldestId, session);
            if (session !== selectedSessionRef.current) return;
            console.log('Loaded:', result.posts.length, 'has_more:', result.has_more);
            if (result.posts.length > 0) {
                setPosts(prev => dedupePosts([...result.posts, ...(prev || [])]));
                setHasMore(result.has_more);
            } else {
                setHasMore(false);
            }
        } catch (error) {
            console.error('Failed to load more posts:', error);
        }
    }, [posts, timelineRef]);

    useEffect(() => {
        loadMoreRef.current = loadMore;
    }, [loadMore]);
    
    // Handle hashtag click
    const handleHashtagClick = useCallback(async (hashtag) => {
        setCurrentHashtag(hashtag);
        setPosts(null); // Show loading
        try {
            const result = await getPostsByHashtag(hashtag);
            setPosts(result.posts);
            setHasMore(false);
        } catch (error) {
            console.error('Failed to load hashtag posts:', error);
        }
    }, []);
    
    // Go back to timeline
    const handleBackToTimeline = useCallback(async () => {
        setCurrentHashtag(null);
        setSearchQuery(null);
        setPosts(null);
        try {
            const session = selectedSessionRef.current;
                const result = await getTimeline(10, null, session);
                if (session !== selectedSessionRef.current) return;
            setPosts(result.posts);
            setHasMore(result.has_more);
        } catch (error) {
            console.error('Failed to load timeline:', error);
        }
    }, []);

    // Handle search
    const handleSearch = useCallback(async (query, filters = {}) => {
        if (!query || !query.trim()) return;
        const generation = ++searchGeneration.current;
        const session = selectedSessionRef.current;
        setSearchQuery(query.trim());
        setCurrentHashtag(null);
        setPosts(null);
        try {
            const result = await searchPosts(query.trim(), 50, 0, { ...filters, sessionId: filters.scope === 'all' ? undefined : session });
            if (generation !== searchGeneration.current || session !== selectedSessionRef.current) return;
            setPosts(result.results);
            setHasMore(false);
        } catch (error) {
            if (generation !== searchGeneration.current || session !== selectedSessionRef.current) return;
            console.error('Failed to search:', error);
            setPosts([]);
        }
    }, []);
    
    const enterSearchMode = useCallback(() => {
        setSearchOpen(true);
        setSearchQuery(null);
        setCurrentHashtag(null);
        setPosts([]);
    }, []);
    
    const exitSearchMode = useCallback(() => {
        searchGeneration.current++;
        setSearchOpen(false);
        setSearchQuery(null);
        loadPosts();
    }, [loadPosts]);

    const navigateToSearchResult = useCallback(() => {}, []);

    const animateAndRemovePosts = useCallback((ids) => {
        if (!ids?.length) return;
        const idSet = new Set(ids);
        setRemovingPostIds((prev) => new Set([...prev, ...idSet]));
        setTimeout(() => {
            setPosts((prev) => prev ? prev.filter((item) => !idSet.has(item.id)) : prev);
            setRemovingPostIds((prev) => {
                const next = new Set(prev);
                ids.forEach((id) => next.delete(id));
                return next;
            });
        }, 200);
    }, []);

    const handleDeletePost = useCallback(async (post) => {
        if (!post) return;
        const postId = post.id;
        const replyCount = posts?.filter((item) => item?.data?.thread_id === postId).length || 0;
        if (replyCount > 0) {
            const confirmed = window.confirm(`Delete this message and its ${replyCount} replies?`);
            if (!confirmed) return;
        }
        try {
            const result = await deletePost(postId, replyCount > 0);
            if (result?.ids?.length) {
                animateAndRemovePosts(result.ids);
                if (hasMore) {
                    await loadMore();
                }
            }
        } catch (error) {
            const errorMessage = error?.message || '';
            if (replyCount === 0 && errorMessage.includes('Replies exist')) {
                const confirmed = window.confirm('Delete this message and its replies?');
                if (!confirmed) return;
                const result = await deletePost(postId, true);
                if (result?.ids?.length) {
                    animateAndRemovePosts(result.ids);
                    if (hasMore) {
                        await loadMore();
                    }
                }
                return;
            }
            console.error('Failed to delete post:', error);
            alert(`Failed to delete message: ${errorMessage}`);
        }
    }, [hasMore, loadMore, posts, animateAndRemovePosts]);

    const handleOpenAttachmentPreview = useCallback((attachment) => {
        if (!attachment) return;
        if (attachment.id) {
            window.open(getMediaUrl(attachment.id), '_blank', 'noopener');
        }
    }, []);

    const loadAgents = useCallback(async () => {
        try {
            const data = await getAgents();
            setAgents(buildAgentsMap(data));
            const defaultAgent = (data?.agents || []).find((agent) => agent.id === 'default');
            setActiveModel(resolveAgentModel(defaultAgent));
            applyBranding(defaultAgent?.name, defaultAgent?.avatar_url);
            const nextUser = data?.user || {};
            setUserProfile((prev) => {
                const nextName = typeof nextUser.name === 'string' && nextUser.name.trim() ? nextUser.name.trim() : 'You';
                const nextAvatar = typeof nextUser.avatar_url === 'string' ? nextUser.avatar_url.trim() : null;
                const nextBg = typeof nextUser.avatar_background === 'string' && nextUser.avatar_background.trim()
                    ? nextUser.avatar_background.trim() : null;
                if (prev.name === nextName && prev.avatar_url === nextAvatar && prev.avatar_background === nextBg) return prev;
                return { name: nextName, avatar_url: nextAvatar, avatar_background: nextBg };
            });
        } catch (e) {
            console.warn('Failed to load agents:', e);
        }
    }, [applyBranding]);

    const expandAgentPanel = useCallback(async (panelKey, turnId) => {
        if (!turnId || (panelKey !== 'draft' && panelKey !== 'thought')) return;
        try {
            const data = await getAgentTurnPreview(turnId);
            if (panelKey === 'draft') {
                const text = String(data?.draft || '');
                const totalLines = Number.isFinite(data?.draft_total_lines)
                    ? data.draft_total_lines
                    : (text ? text.replace(/\r\n/g, '\n').split('\n').length : 0);
                draftBufferRef.current = text;
                setAgentDraft({ text, totalLines });
                return;
            }
            const text = String(data?.thought || '');
            const totalLines = Number.isFinite(data?.thought_total_lines)
                ? data.thought_total_lines
                : (text ? text.replace(/\r\n/g, '\n').split('\n').length : 0);
            thoughtBufferRef.current = text;
            setAgentThought({ text, totalLines });
        } catch (e) {
            console.warn('Failed to load full agent preview:', e);
        }
    }, []);

    const handlePanelExpandedChange = useCallback((panelKey, expanded, turnId = null) => {
        if (panelKey !== 'draft' && panelKey !== 'thought') return;
        expandedPanelsRef.current = { ...expandedPanelsRef.current, [panelKey]: Boolean(expanded) };
        const activeTurn = turnId || currentTurnIdRef.current;
        if (!activeTurn) return;
        setAgentTurnPanelExpanded(activeTurn, panelKey, expanded).catch((e) => {
            console.warn('Failed to set panel state:', e);
        });
    }, []);

    const handleQueueRemove = useCallback(async (rowId) => {
        if (rowId == null) return;
        try {
            await removeAgentQueueItem(rowId);
            await refreshSelectedQueue();
        } catch (error) {
            console.error('Failed to remove queued item:', error);
            alert('Failed to remove queued item: ' + error.message);
        }
    }, []);

    const handleQueueReorder = useCallback(async (rowId, direction) => {
        try {
            const result = await reorderAgentQueueItem(rowId, direction);
            await refreshSelectedQueue();
        } catch (err) { alert(err.message || 'Failed to reorder queue.'); }
    }, []);

    const handleQueueSteer = useCallback(async (rowId) => {
        if (rowId == null) return;
        try {
            await steerAgentQueueItem(rowId);
            await refreshSelectedQueue();
        } catch (error) {
            console.error('Failed to steer queued item:', error);
            alert('Failed to steer queued item: ' + error.message);
        }
    }, []);

    const applyModelState = useCallback((payload) => {
        if (!payload || typeof payload !== 'object') return;
        const nextModel = payload.model ?? payload.current;
        if (nextModel !== undefined) setActiveModel(nextModel);
        if (payload.thinking_level !== undefined) setActiveThinkingLevel(payload.thinking_level ?? null);
        if (payload.supports_thinking !== undefined) setSupportsThinking(Boolean(payload.supports_thinking));
    }, []);

    useEffect(() => {
        loadAgents();

        const saved = parseInt(localStorage.getItem('sidebarWidth') || '', 10);
        const width = Number.isFinite(saved) ? Math.min(Math.max(saved, 160), 600) : 280;
        sidebarWidthRef.current = width;
        if (appShellRef.current) {
            appShellRef.current.style.setProperty('--sidebar-width', `${width}px`);
        }

        const savedEditor = parseInt(localStorage.getItem('editorWidth') || '', 10);
        const editorW = Number.isFinite(savedEditor) ? Math.min(Math.max(savedEditor, 200), window.innerWidth * 0.7) : 280;
        editorWidthRef.current = editorW;
        if (appShellRef.current) {
            appShellRef.current.style.setProperty('--editor-width', `${editorW}px`);
        }
    }, [loadAgents]);

    // Silence detection timer
    useEffect(() => {
        const intervalMs = Math.min(1000, Math.max(100, Math.floor(SILENCE_WARNING_MS / 2)));
        const interval = setInterval(() => {
            if (!isAgentRunningRef.current) return;
            if (pendingRequestRef.current) return;
            const lastEvent = lastAgentEventRef.current;
            if (!lastEvent) return;
            const now = Date.now();
            const silenceMs = now - lastEvent;

            if (silenceMs >= SILENCE_FINALIZE_MS) {
                finalizeStalledResponse();
                return;
            }

            if (silenceMs >= SILENCE_WARNING_MS) {
                if (now - lastSilenceNoticeRef.current >= SILENCE_REFRESH_MS) {
                    const seconds = Math.floor(silenceMs / 1000);
                    setAgentStatus({
                        type: 'waiting',
                        title: `Waiting for model… No events for ${seconds}s`,
                    });
                    lastSilenceNoticeRef.current = now;
                }
            }
        }, intervalMs);

        return () => clearInterval(interval);
    }, [finalizeStalledResponse]);

    const handleSseEvent = useCallback((eventType, data) => {
        if (['agent_followup_queued', 'agent_followup_consumed', 'agent_followup_removed', 'agent_queue_reordered', 'agent_steer_queued'].includes(eventType)) {
            refreshSelectedQueue().catch(error => console.warn('Queue refresh failed:', error));
            return;
        }
        if (!eventMatchesSession(eventType, data, selectedSessionRef.current)) return;
        const turnId = data?.turn_id;
        if (eventType === 'session_model_changed') {
            modelGeneration.current++;
            const model = data.model;
            setActiveModel(model ? [model.provider, model.id || model.name].filter(Boolean).join('/') : null);
            setActiveThinkingLevel(data.thinking_level ?? null);
            setSupportsThinking(model?.reasoning === true);
            return;
        }

        if (eventType === 'connected') {
            setAgentStatus(null);
            setAgentDraft({ text: '', totalLines: 0 });
            setAgentPlan('');
            setAgentThought({ text: '', totalLines: 0 });
            setPendingRequest(null);
            pendingRequestRef.current = null;
            clearAgentRunState();
            return;
        }

        if (selectedSessionRef.current !== 'default' && ['model_changed', 'agent_followup_queued', 'agent_steer_queued', 'agent_queue_reordered'].includes(eventType)) return;
        updateAgentProfile(data);
        updateUserProfile(data);

        if (eventType === 'agent_status') {
            if (data.type === 'done' || data.type === 'error' || data.type === 'cancelled') {
                if (turnId && currentTurnIdRef.current && turnId !== currentTurnIdRef.current) {
                    return;
                }
                // Refresh timeline to surface any final response that arrived
                // during an SSE gap (agent_response event may have been missed).
                const { currentHashtag: ah, searchQuery: sq } = viewStateRef.current || {};
                if (!ah && !sq) loadPosts();
                wasAgentActiveRef.current = false;
                clearAgentRunState();
                setAgentStatus(null);
                setAgentDraft({ text: '', totalLines: 0 });
                setAgentPlan('');
                setAgentThought({ text: '', totalLines: 0 });
                setPendingRequest(null);
                // Refresh context usage after turn completes
                getAgentContext().then(ctx => { if (ctx && ctx.percent != null) setContextUsage(selectedSessionRef.current === 'default' ? ctx : null); }).catch(() => {});
            } else {
                wasAgentActiveRef.current = true;
                if (turnId) setActiveTurn(turnId);
                noteAgentActivity({ running: true, clearSilence: true });
                if (data.type === 'thinking') {
                    draftBufferRef.current = '';
                    thoughtBufferRef.current = '';
                    expandedPanelsRef.current = { draft: false, thought: false };
                    setAgentDraft({ text: '', totalLines: 0 });
                    setAgentPlan('');
                    setAgentThought({ text: '', totalLines: 0 });
                }
                setAgentStatus(data);
            }
            return;
        }

        if (eventType === 'agent_draft_delta') {
            if (turnId && currentTurnIdRef.current && turnId !== currentTurnIdRef.current) {
                return;
            }
            if (turnId && !currentTurnIdRef.current) {
                setActiveTurn(turnId);
            }
            noteAgentActivity({ running: true, clearSilence: true });
            if (data?.reset) {
                draftBufferRef.current = '';
            }
            if (data?.delta) {
                draftBufferRef.current += data.delta;
            }
            if (expandedPanelsRef.current.draft) {
                const fullText = draftBufferRef.current;
                setAgentDraft({ text: fullText, totalLines: estimatePreviewLines(fullText) });
            }
            return;
        }

        if (eventType === 'agent_draft') {
            if (turnId && currentTurnIdRef.current && turnId !== currentTurnIdRef.current) {
                return;
            }
            if (turnId && !currentTurnIdRef.current) {
                setActiveTurn(turnId);
            }
            noteAgentActivity({ running: true, clearSilence: true });
            const text = data.text || '';
            const mode = data.mode || (data.kind === 'plan' ? 'replace' : 'append');
            const inferredTotal = Number.isFinite(data.total_lines)
                ? data.total_lines
                : (text ? text.replace(/\r\n/g, '\n').split('\n').length : 0);

            if (data.kind === 'plan') {
                if (mode === 'replace') setAgentPlan(text);
                else setAgentPlan((prev) => (prev || '') + text);
            } else {
                if (!expandedPanelsRef.current.draft) {
                    draftBufferRef.current = text;
                    setAgentDraft({ text, totalLines: inferredTotal });
                }
            }
            return;
        }

        if (eventType === 'agent_thought_delta') {
            if (turnId && currentTurnIdRef.current && turnId !== currentTurnIdRef.current) {
                return;
            }
            if (turnId && !currentTurnIdRef.current) {
                setActiveTurn(turnId);
            }
            noteAgentActivity({ running: true, clearSilence: true });
            if (data?.reset) {
                thoughtBufferRef.current = '';
            }
            if (data?.delta) {
                thoughtBufferRef.current += data.delta;
            }
            if (expandedPanelsRef.current.thought) {
                const fullText = thoughtBufferRef.current;
                setAgentThought({ text: fullText, totalLines: estimatePreviewLines(fullText) });
            }
            return;
        }

        if (eventType === 'agent_thought') {
            if (turnId && currentTurnIdRef.current && turnId !== currentTurnIdRef.current) {
                return;
            }
            if (turnId && !currentTurnIdRef.current) {
                setActiveTurn(turnId);
            }
            noteAgentActivity({ running: true, clearSilence: true });
            const text = data.text || '';
            const inferredTotal = Number.isFinite(data.total_lines)
                ? data.total_lines
                : (text ? text.replace(/\r\n/g, '\n').split('\n').length : 0);
            if (!expandedPanelsRef.current.thought) {
                thoughtBufferRef.current = text;
                setAgentThought({ text, totalLines: inferredTotal });
            }
            return;
        }

        // Handle agent requests (permission, choices)
        if (eventType === 'agent_request') {
            console.log('Agent request:', data);
            if (turnId && currentTurnIdRef.current && turnId !== currentTurnIdRef.current) {
                return;
            }
            if (turnId) setActiveTurn(turnId);
            noteAgentActivity({ running: true, clearSilence: true });
            setPendingRequest(data);
            pendingRequestRef.current = data;
            return;
        }

        if (eventType === 'agent_request_timeout') {
            console.log('Agent request timeout:', data);
            if (turnId && currentTurnIdRef.current && turnId !== currentTurnIdRef.current) {
                return;
            }
            setPendingRequest(null);
            pendingRequestRef.current = null;
            clearAgentRunState();
            setAgentStatus({ type: 'error', title: 'Permission request timed out' });
            return;
        }

        if (eventType === 'agent_steer_queued') {
            if (typeof data?.row_id === 'number') {
                setQueuedFollowups((prev) => prev.filter((item) => item.row_id !== data.row_id));
            }
            if (turnId && currentTurnIdRef.current && turnId !== currentTurnIdRef.current) {
                return;
            }
            const targetTurn = turnId || currentTurnIdRef.current;
            if (!targetTurn) return;
            steerQueuedTurnIdRef.current = targetTurn;
            setSteerQueuedTurnId(targetTurn);
            return;
        }

        if (eventType === 'agent_queue_reordered') {
            setQueuedFollowups(data.items || []);
            return;
        }
        if (eventType === 'agent_followup_queued') {
            setQueuedFollowups((prev) => {
                if (prev.some((item) => item.row_id === data?.row_id)) return prev;
                return [...prev, data];
            });
            return;
        }

        if (eventType === 'agent_followup_consumed' || eventType === 'agent_followup_removed') {
            setQueuedFollowups((prev) => prev.filter((item) => item.row_id !== data?.row_id));
            return;
        }

        if (eventType === 'model_changed') {
            if (data?.model !== undefined) setActiveModel(data.model);
            if (data?.thinking_level !== undefined) setActiveThinkingLevel(data.thinking_level ?? null);
            if (data?.supports_thinking !== undefined) setSupportsThinking(Boolean(data.supports_thinking));
            return;
        }

        if (eventType === 'workspace_update') {
            if (typeof window !== 'undefined') {
                window.dispatchEvent(new CustomEvent('workspace-update', { detail: data }));
            }
            return;
        }

        if (eventType === 'ui_theme') {
            applyUiTheme(data);
            return;
        }

        // Add new posts/replies to timeline (only when on main timeline) - append at end for chat style
        const { currentHashtag: activeHashtag, searchQuery: activeSearch } = viewStateRef.current;
        const responseFallback = eventType === 'agent_response' ? (draftBufferRef.current || '').trim() : '';
        if (eventType === 'agent_response') {
            removeStalledPost();
            lastAgentResponseRef.current = {
                post: data,
                turnId: currentTurnIdRef.current,
            };
            clearAgentRunState();
            setAgentStatus(null);
            setAgentDraft({ text: '', totalLines: 0 });
            setAgentPlan('');
            setAgentThought({ text: '', totalLines: 0 });
            setPendingRequest(null);
            notifyForFinalResponse();
        }
        if (!activeHashtag && !activeSearch && (eventType === 'new_post' || eventType === 'agent_response')) {
            if (eventType === 'agent_response') {
                const content = data?.data?.content;
                if (!content || !String(content).trim()) {
                    if (responseFallback) {
                        data = {
                            ...data,
                            data: {
                                ...data.data,
                                content: responseFallback,
                            },
                        };
                    }
                }
                const resolvedContent = data?.data?.content;
                const hasText = !!(resolvedContent && String(resolvedContent).trim());
                const hasMedia = Array.isArray(data?.data?.media_ids) && data.data.media_ids.length > 0;
                const hasBlocks = Array.isArray(data?.data?.content_blocks) && data.data.content_blocks.some((block) => {
                    if (!block || typeof block !== 'object') return false;
                    if (block.type === 'image' || block.type === 'file') return true;
                    if (block.type === 'text') return !!String(block.text || '').trim();
                    return false;
                });
                if (!hasText && !hasMedia && !hasBlocks) {
                    return;
                }
            }
            setPosts(prev => {
                if (!prev) return [data];
                if (prev.some((post) => post.id === data.id)) return prev;
                return [...prev, data];
            });
            scrollToBottomRef.current?.();
        }
        // Update existing post (e.g., when link previews are fetched)
        if (eventType === 'interaction_updated') {
            setPosts(prev => prev ? prev.map(p => p.id === data.id ? data : p) : prev);
        }
        if (eventType === 'interaction_deleted') {
            const ids = data?.ids || [];
            if (ids.length) {
                setPosts(prev => prev ? prev.filter(p => !ids.includes(p.id)) : prev);
                const vs = viewStateRef.current;
                if (hasMoreRef.current && !vs.currentHashtag && !vs.searchQuery) {
                    loadMoreRef.current?.();
                }
            }
        }
        if (eventType === 'agents_changed') {
            loadAgents();
        }
    }, [clearAgentRunState, loadAgents, setActiveTurn, noteAgentActivity, removeStalledPost, updateAgentProfile, updateUserProfile]);

    // Set up SSE connection
    useEffect(() => {
        loadPosts();
        
        const sse = new SSEClient(handleSseEvent, handleConnectionStatusChange);
        
        sse.connect();

        let reconnectTimer = null;
        const handleWindowFocus = () => {
            if (document.visibilityState === 'hidden') return;
            if (reconnectTimer) clearTimeout(reconnectTimer);
            reconnectTimer = setTimeout(() => {
                reconnectTimer = null;
                sse.reconnectIfNeeded();
            }, 150);
        };
        window.addEventListener('focus', handleWindowFocus);
        document.addEventListener('visibilitychange', handleWindowFocus);
        
        return () => {
            if (reconnectTimer) clearTimeout(reconnectTimer);
            window.removeEventListener('focus', handleWindowFocus);
            document.removeEventListener('visibilitychange', handleWindowFocus);
            sse.disconnect();
        };
    }, [loadPosts, handleSseEvent]);

    // Adaptive backstop poller — SSE is the primary event source; this is
    // a safety net only. 15 s when a turn is active, 60 s when idle.
    // When active, also polls /agents/status to detect long-running agent
    // activity and update the UI if SSE events are lagging.
    const isAgentActive = agentStatus !== null;
    useEffect(() => {
        if (connectionStatus !== 'connected') return;
        const intervalMs = isAgentActive ? 15000 : 60000;
        const interval = setInterval(async () => {
            if (isAgentActive) {
                // Poll server to verify agent is still active and update status
                try {
                    const statusSession = selectedSessionRef.current;
                    const statusData = await getAgentStatus(statusSession);
                    if (selectedSessionRef.current !== statusSession) return;
                    if (!statusData) return;
                    syncQueueState(statusData);
                    const turns = statusData.active_turns || [];
                    if (turns.length > 0) {
                        const turn = turns[turns.length - 1];
                        const lastStatus = turn.last_status;
                        if (lastStatus && turn.turn_id === currentTurnIdRef.current) {
                            noteAgentActivity({ running: true });
                            // Only update status bar with server state for non-streaming types
                            const statusType = lastStatus.type;
                            if (statusType && statusType !== 'done' && statusType !== 'error' && statusType !== 'cancelled') {
                                setAgentStatus({
                                    thread_id: turn.thread_id,
                                    agent_id: turn.agent_id,
                                    turn_id: turn.turn_id,
                                    ...lastStatus,
                                });
                            }
                        }
                        // Refresh context usage while agent is working
                        getAgentContext().then(ctx => {
                            if (ctx && ctx.percent != null) setContextUsage(selectedSessionRef.current === 'default' ? ctx : null);
                        }).catch(() => {});
                    } else if (!statusData.busy) {
                        // Server says no active turns but UI thinks agent is active —
                        // the done/error SSE event was likely lost.
                        if (isAgentRunningRef.current) {
                            const { currentHashtag: ah, searchQuery: sq } = viewStateRef.current || {};
                            if (!ah && !sq) loadPosts();
                            clearAgentRunState();
                            setAgentStatus(null);
                            setAgentDraft({ text: '', totalLines: 0 });
                            setAgentPlan('');
                            setAgentThought({ text: '', totalLines: 0 });
                            // Refresh context usage since the turn completed
                            getAgentContext().then(ctx => {
                                if (ctx && ctx.percent != null) setContextUsage(selectedSessionRef.current === 'default' ? ctx : null);
                            }).catch(() => {});
                        }
                    }
                } catch {
                    // ignore polling errors
                }
            } else {
                const { currentHashtag: activeHashtag, searchQuery: activeSearch } = viewStateRef.current || {};
                if (!activeHashtag && !activeSearch) {
                    loadPosts();
                }
            }
        }, intervalMs);
        return () => clearInterval(interval);
    }, [connectionStatus, isAgentActive, loadPosts, clearAgentRunState, noteAgentActivity, syncQueueState]);

    const handleSplitterMouseDown = useRef((e) => {
        e.preventDefault();
        const shell = appShellRef.current;
        if (!shell) return;
        const startX = e.clientX;
        const startW = sidebarWidthRef.current || 280;
        const splitter = e.currentTarget;
        splitter.classList.add('dragging');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';

        let lastX = startX;
        const onMove = (me) => {
            lastX = me.clientX;
            const width = Math.min(Math.max(startW + (me.clientX - startX), 160), 600);
            shell.style.setProperty('--sidebar-width', `${width}px`);
            sidebarWidthRef.current = width;
        };
        const onUp = () => {
            const width = Math.min(Math.max(startW + (lastX - startX), 160), 600);
            sidebarWidthRef.current = width;
            splitter.classList.remove('dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            localStorage.setItem('sidebarWidth', String(Math.round(width)));
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    }).current;

    const handleSplitterTouchStart = useRef((e) => {
        e.preventDefault();
        const shell = appShellRef.current;
        if (!shell) return;
        const touch = e.touches[0];
        if (!touch) return;
        const startX = touch.clientX;
        const startW = sidebarWidthRef.current || 280;
        const splitter = e.currentTarget;
        splitter.classList.add('dragging');
        document.body.style.userSelect = 'none';

        const onMove = (te) => {
            const t = te.touches[0];
            if (!t) return;
            te.preventDefault();
            const width = Math.min(Math.max(startW + (t.clientX - startX), 160), 600);
            shell.style.setProperty('--sidebar-width', `${width}px`);
            sidebarWidthRef.current = width;
        };
        const onUp = () => {
            splitter.classList.remove('dragging');
            document.body.style.userSelect = '';
            localStorage.setItem('sidebarWidth', String(Math.round(sidebarWidthRef.current || startW)));
            document.removeEventListener('touchmove', onMove);
            document.removeEventListener('touchend', onUp);
            document.removeEventListener('touchcancel', onUp);
        };
        document.addEventListener('touchmove', onMove, { passive: false });
        document.addEventListener('touchend', onUp);
        document.addEventListener('touchcancel', onUp);
    }).current;

    const handleEditorSplitterMouseDown = useRef((e) => {
        e.preventDefault();
        const shell = appShellRef.current;
        if (!shell) return;
        const startX = e.clientX;
        const startW = editorWidthRef.current || sidebarWidthRef.current || 280;
        const splitter = e.currentTarget;
        splitter.classList.add('dragging');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';

        let lastX = startX;
        const onMove = (me) => {
            lastX = me.clientX;
            const width = Math.min(Math.max(startW + (me.clientX - startX), 200), 800);
            shell.style.setProperty('--editor-width', `${width}px`);
            editorWidthRef.current = width;
        };
        const onUp = () => {
            const width = Math.min(Math.max(startW + (lastX - startX), 200), 800);
            editorWidthRef.current = width;
            splitter.classList.remove('dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            localStorage.setItem('editorWidth', String(Math.round(width)));
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    }).current;

    const handleEditorSplitterTouchStart = useRef((e) => {
        e.preventDefault();
        const shell = appShellRef.current;
        if (!shell) return;
        const touch = e.touches[0];
        if (!touch) return;
        const startX = touch.clientX;
        const startW = editorWidthRef.current || sidebarWidthRef.current || 280;
        const splitter = e.currentTarget;
        splitter.classList.add('dragging');
        document.body.style.userSelect = 'none';

        const onMove = (te) => {
            const t = te.touches[0];
            if (!t) return;
            te.preventDefault();
            const width = Math.min(Math.max(startW + (t.clientX - startX), 200), 800);
            shell.style.setProperty('--editor-width', `${width}px`);
            editorWidthRef.current = width;
        };
        const onUp = () => {
            splitter.classList.remove('dragging');
            document.body.style.userSelect = '';
            localStorage.setItem('editorWidth', String(Math.round(editorWidthRef.current || startW)));
            document.removeEventListener('touchmove', onMove);
            document.removeEventListener('touchend', onUp);
            document.removeEventListener('touchcancel', onUp);
        };
        document.addEventListener('touchmove', onMove, { passive: false });
        document.addEventListener('touchend', onUp);
        document.addEventListener('touchcancel', onUp);
    }).current;

    const editorOpen = editorTabs.length > 0;
    const activeEditorTab = editorTabs.find((tab) => tab.id === activeEditorTabId) || editorTabs[editorTabs.length - 1] || null;
    const previewOpen = activeEditorTab ? previewTabs.has(activeEditorTab.id) : false;
    
    return html`
        <div class=${`app-shell${workspaceOpen ? '' : ' workspace-collapsed'}${editorOpen ? ' editor-open' : ''}${popoutMode ? ' popout-mode' : ''}${terminalPopout ? ' terminal-popout' : ''}`} ref=${appShellRef}>
            ${terminalEnabled && !terminalVisible && !terminalPopout && html`<button class="terminal-open-button" onClick=${() => setTerminalVisible(true)} title="Open terminal">Terminal</button>`}
            ${!popoutMode && html`<${WorkspaceExplorer} onFileSelect=${addFileRef} onFolderSelect=${path => setFolderRefs(prev => prev.includes(path) ? prev : [...prev, path])} visible=${workspaceOpen} active=${workspaceOpen || editorOpen} onOpenEditor=${openEditor} renderMarkdown=${renderMarkdown} />`}
            ${!popoutMode && html`<button
                class=${`workspace-toggle-tab${workspaceOpen ? ' open' : ' closed'}`}
                onClick=${toggleWorkspace}
                title=${workspaceOpen ? 'Hide workspace' : 'Show workspace'}
                aria-label=${workspaceOpen ? 'Hide workspace' : 'Show workspace'}
            >
                <svg class="workspace-toggle-tab-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <polyline points="6 3 11 8 6 13" />
                </svg>
            </button>`}
            ${!popoutMode && html`<div class="workspace-splitter" onMouseDown=${handleSplitterMouseDown} onTouchStart=${handleSplitterTouchStart}></div>`}
            ${(editorOpen || terminalVisible) && html`
                <div class="editor-pane-container">
                ${editorOpen && html`<div class="editor-stack">
                    <${TabStrip}
                        tabs=${editorTabs}
                        activeId=${activeEditorTab?.id}
                        onActivate=${handleTabActivate}
                        onClose=${closeEditorTab}
                        onCloseOthers=${handleTabCloseOthers}
                        onCloseAll=${handleTabCloseAll}
                        onTogglePin=${handleTabTogglePin}
                        onTogglePreview=${handleTabTogglePreview}
                        previewTabs=${previewTabs}
                        onPopOutTab=${!popoutMode ? handlePopOutTab : undefined}
                    />
                    <${WorkspaceEditor}
                        key=${activeEditorTab?.id || 'editor'}
                        path=${activeEditorTab?.path}
                        content=${activeEditorTab?.content}
                        savedContent=${activeEditorTab?.savedContent}
                        loading=${activeEditorTab?.loading}
                        error=${activeEditorTab?.error}
                        saving=${activeEditorTab?.saving}
                        saveError=${activeEditorTab?.saveError}
                        savedAt=${activeEditorTab?.savedAt}
                        onSave=${handleEditorSave}
                        onClose=${closeEditor}
                        onChange=${handleEditorChange}
                        showPreview=${previewOpen}
                        onClosePreview=${() => handleTabTogglePreview(activeEditorTab?.id)}
                        renderMarkdown=${renderMarkdown}
                        renderMermaidDiagrams=${renderMermaidDiagrams}
                    />
                </div>`}
                ${terminalVisible && html`<${TerminalPanel} shared=${editorOpen} popout=${terminalPopout} onClose=${() => { setTerminalVisible(false); if (terminalPopout) window.close(); }} />`}
                </div>
                ${!popoutMode && !terminalPopout && html`<div class="editor-splitter" onMouseDown=${handleEditorSplitterMouseDown} onTouchStart=${handleEditorSplitterTouchStart}></div>`}
            `}
            ${!popoutMode && html`<div class="container">
                ${searchQuery && isIOSDevice() && html`<div class="search-results-spacer"></div>`}
                ${(currentHashtag || searchQuery) && html`
                    <div class="hashtag-header">
                        <button class="back-btn" onClick=${handleBackToTimeline}>
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                        </button>
                        <span>${currentHashtag ? `#${currentHashtag}` : `Search: ${searchQuery}`}</span>
                    </div>
                `}
                <${Timeline} 
                    posts=${posts}
                    hasMore=${hasMore}
                    onLoadMore=${loadMore}
                    timelineRef=${timelineRef}
                    onHashtagClick=${handleHashtagClick}
                    onMessageRef=${addMessageRef}
                    onScrollToMessage=${scrollToMessage}
                    onPostClick=${undefined}
                    onDeletePost=${handleDeletePost}
                    onOpenAttachmentPreview=${handleOpenAttachmentPreview}
                    emptyMessage=${currentHashtag ? `No posts with #${currentHashtag}` : searchQuery ? `No results for "${searchQuery}"` : undefined}
                    agents=${agents}
                    user=${userProfile}
                    reverse=${!(searchQuery && !currentHashtag)}
                    removingPostIds=${removingPostIds}
                    searchQuery=${searchQuery}
                    renderMarkdown=${renderMarkdown}
                    renderMermaidDiagrams=${renderMermaidDiagrams}
                    getAgentName=${getAgentName}
                    getAgentAvatar=${getAgentAvatar}
                    getAvatarInfo=${getAvatarInfo}
                    formatTime=${formatTime}
                    formatCount=${formatCount}
                />
                <${AgentStatus}
                    status=${agentStatus}
                    draft=${agentDraft}
                    plan=${agentPlan}
                    thought=${agentThought}
                    pendingRequest=${pendingRequest}
                    turnId=${currentTurnId}
                    steerQueued=${Boolean(steerQueuedTurnId && (steerQueuedTurnId === (agentStatus?.turn_id || currentTurnId)))}
                    renderThinkingMarkdown=${renderThinkingMarkdown}
                    getTurnColor=${getTurnColor}
                    onExpandPanel=${expandAgentPanel}
                    onPanelExpandedChange=${handlePanelExpandedChange}
                />
                <button class="session-trigger" data-testid="session-switcher" onClick=${async () => { try { await refreshSessions(); setSessionPickerOpen(v => !v); } catch (err) { alert(err.message); } }}>Session: ${sessionOptions.find(s => s.id === selectedSession)?.name || selectedSession}</button>
                ${sessionPickerOpen && html`<${SessionPicker} sessions=${sessionOptions} currentId=${selectedSession} onSelect=${async id => { if (sessionOptions.find(item => item.id === id)?.archived) { await updateSession(id, { archived: false }); await refreshSessions(); } await selectSession(id); }} onClose=${() => setSessionPickerOpen(false)}
                    onCreate=${() => { createdSessionRef.current = null; setCreatingSession(true); }}
                    onRename=${id => setRenamingSession(sessionOptions.find(item => item.id === id))}
                    onArchive=${async (id, archived) => { await updateSession(id, { archived }); if (archived && id === selectedSession) await selectSession('default'); await refreshSessions(); }}
                    onPin=${async (id, pinned) => { await updateSession(id, { pinned }); await refreshSessions(); }}
                    onDelete=${async id => { if (!confirm('Delete empty session?')) return; await deleteSession(id); if (id === selectedSession) await selectSession('default'); await refreshSessions(); }} />`}
                <${ComposeBox} key=${selectedSession} sessionId=${selectedSession}
                    onPost=${() => { loadPosts(); scrollToBottom(); }}
                    onFocus=${scrollToBottom}
                    searchMode=${searchOpen}
                    onSearch=${handleSearch}
                    onEnterSearch=${enterSearchMode}
                    onExitSearch=${exitSearchMode}
                    folderRefs=${folderRefs}
                    onRemoveFolderRef=${path => setFolderRefs(prev => prev.filter(item => item !== path))}
                    onClearFolderRefs=${() => setFolderRefs([])}
                    fileRefs=${fileRefs}
                    onRemoveFileRef=${removeFileRef}
                    onClearFileRefs=${clearFileRefs}
                    messageRefs=${messageRefs}
                    onRemoveMessageRef=${removeMessageRef}
                    onClearMessageRefs=${clearMessageRefs}
                    activeModel=${activeModel}
                    thinkingLevel=${activeThinkingLevel}
                    supportsThinking=${supportsThinking}
                    contextUsage=${contextUsage}
                    queuedFollowups=${queuedFollowups}
                    onQueueRemove=${handleQueueRemove}
                    onQueueSteer=${handleQueueSteer}
                    onQueueReorder=${handleQueueReorder}
                    onModelChange=${setActiveModel}
                    onModelStateChange=${applyModelState}
                    notificationsEnabled=${notificationsEnabled}
                    notificationPermission=${notificationPermission}
                    onToggleNotifications=${handleToggleNotifications}
                />
                ${renamingSession && html`<${SessionNameDialog} key=${renamingSession.id} name=${renamingSession.name} onClose=${() => setRenamingSession(null)} onSave=${async name => { await updateSession(renamingSession.id, { name }); await refreshSessions(); }} />`}
            ${creatingSession && html`<${SessionNameDialog} creating=${true} onClose=${() => setCreatingSession(false)} onSave=${async name => { if (!createdSessionRef.current) { const result = await createSession(name); createdSessionRef.current = result.session.id; } await refreshSessions(); await selectSession(createdSessionRef.current); }} />`}
            <${ConnectionStatus} status=${connectionStatus} />
                <${AgentRequestModal} request=${pendingRequest} onRespond=${() => setPendingRequest(null)} />
            </div>`}
        </div>
    `;
}

// Mount the app
render(html`<${App} />`, document.getElementById('app'));
