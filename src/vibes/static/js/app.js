import { html, render, useState, useEffect, useCallback, useRef, useMemo } from './vendor/preact-htm.js';
import { getTimeline, getPostsByHashtag, searchPosts, getThread, createPost, deletePost, sendAgentMessage, uploadMedia, getThumbnailUrl, getMediaUrl, getMediaInfo, respondToAgentRequest, addToWhitelist, getAgents, getAgentTurnPreview, setAgentTurnPanelExpanded, getWorkspaceFile, updateWorkspaceFile, getAgentContext, SSEClient } from './api.js';
import { ComposeBox } from './components/compose-box.js';
import { Timeline } from './components/timeline.js';
import { AgentStatus, AgentRequestModal, ConnectionStatus } from './components/status.js';
import { WorkspaceExplorer } from './components/workspace-explorer.js';
import { WorkspaceEditor } from './components/editor.js';

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

// Configure marked for safe rendering
if (window.marked) {
    marked.setOptions({
        breaks: true,  // Convert \n to <br>
        gfm: true,     // GitHub Flavored Markdown
    });
}

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
        const tagContent = isClosing ? trimmed.slice(1) : trimmed;
        const tagName = tagContent.split(/\s+/)[0]?.toLowerCase();
        if (!tagName || !ALLOWED_HTML_TAGS.has(tagName)) return match;
        const slash = isClosing ? '/' : '';
        return `<${slash}${tagName}>`;
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
    if (!window.katex) return html_content;

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
    let html_content = window.marked
        ? marked.parse(safeHtml, { headerIds: false, mangle: false })
        : safeHtml.replace(/\n/g, '<br>');

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
    let html_content = window.marked ? marked.parse(safeHtml) : safeHtml.replace(/\n/g, '<br>');
    html_content = decodeCodeEntities(html_content);
    html_content = decodeTextEntities(html_content);
    return html_content;
}

// Render pending mermaid diagrams in the DOM
async function renderMermaidDiagrams(container) {
    if (!window.beautifulMermaid) return;
    
    const { renderMermaid, THEMES } = window.beautifulMermaid;
    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = isDark ? THEMES['tokyo-night'] : THEMES['github-light'];
    
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

/**
 * Get avatar display info from name and optional image URL.
 * Returns object with { letter, color, image }
 */
function getAvatarInfo(name, avatarUrl = null) {
    if (!name) name = 'Agent';
    const letter = name.charAt(0).toUpperCase();
    
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
    
    return { letter, color, image: avatarUrl || null };
}

function getAgentName(agentId, agents) {
    if (!agentId) return 'Agent';
    const name = agents[agentId]?.name || agentId;
    return name ? name.charAt(0).toUpperCase() + name.slice(1) : 'Agent';
}

function getAgentAvatar(agentId, agents) {
    if (!agentId) return null;
    return agents[agentId]?.avatar || null;
}

/**
 * Update browser theme color (affects mobile chrome and PWA title bar)
 */
function updateThemeColor(dark) {
    const color = dark ? '#000000' : '#ffffff';
    let meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
        meta.setAttribute('content', color);
    }
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
    const [posts, setPosts] = useState(null);
    const [hasMore, setHasMore] = useState(false);
    const [connectionStatus, setConnectionStatus] = useState('disconnected');
    const [currentHashtag, setCurrentHashtag] = useState(null);
    const [searchQuery, setSearchQuery] = useState(null);
    const [searchOpen, setSearchOpen] = useState(false);
    const [fileRefs, setFileRefs] = useState([]);
    const [agentStatus, setAgentStatus] = useState(null);
    const [agentDraft, setAgentDraft] = useState({ text: '', totalLines: 0 });
    const [agentPlan, setAgentPlan] = useState('');
    const [agentThought, setAgentThought] = useState({ text: '', totalLines: 0 });
    const [pendingRequest, setPendingRequest] = useState(null);
    const [currentTurnId, setCurrentTurnId] = useState(null);
    const [steerQueuedTurnId, setSteerQueuedTurnId] = useState(null);
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
        const stored = localStorage.getItem('workspaceOpen');
        return stored === null ? true : stored === 'true';
    });
    const [editorState, setEditorState] = useState({ open: false, path: null, content: '', loading: false, error: null });
    const [editorSaving, setEditorSaving] = useState(false);
    const [editorSaveError, setEditorSaveError] = useState(null);
    const [editorSavedAt, setEditorSavedAt] = useState(null);
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
        setEditorSaveError(null);
        setEditorSavedAt(null);
        setEditorState({ open: true, path, content: '', loading: true, error: null });
        try {
            const data = await getWorkspaceFile(path, 5_000_000, 'edit');
            if (data?.kind === 'text') {
                setEditorState({ open: true, path, content: data.text || '', loading: false, error: null });
            } else {
                setEditorState({ open: true, path, content: '', loading: false, error: 'File is not a text file' });
            }
        } catch (err) {
            setEditorState({ open: true, path, content: '', loading: false, error: err?.message || 'Failed to load file' });
        }
    }, []);

    const closeEditor = useCallback(() => {
        setEditorState({ open: false, path: null, content: '', loading: false, error: null });
        setEditorSaving(false);
        setEditorSaveError(null);
        setEditorSavedAt(null);
    }, []);

    const handleEditorSave = useCallback(async (content) => {
        const path = editorState.path;
        if (!path) return;
        setEditorSaving(true);
        setEditorSaveError(null);
        try {
            await updateWorkspaceFile(path, content);
            setEditorSavedAt(Date.now());
        } catch (err) {
            setEditorSaveError(err?.message || 'Save failed');
        } finally {
            setEditorSaving(false);
        }
    }, [editorState.path]);

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
        const agentId = payload?.agent_id;
        if (!agentId) return;
        const next = {};
        if (payload.agent_name) next.name = payload.agent_name;
        if (Object.prototype.hasOwnProperty.call(payload, 'agent_avatar')) next.avatar = payload.agent_avatar;
        if (Object.keys(next).length === 0) return;
        setAgents((prev) => {
            const current = prev?.[agentId] || { id: agentId };
            const merged = { ...current, ...next, id: agentId };
            if (current.name === merged.name && current.avatar === merged.avatar) return prev;
            return { ...(prev || {}), [agentId]: merged };
        });
        if (agentId === 'default') {
            applyBranding(next.name || null, next.avatar || null);
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
                const result = await getTimeline(10);
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
            return;
        }
        const { currentHashtag: activeHashtag, searchQuery: activeSearch } = viewStateRef.current;
        if (!activeHashtag && !activeSearch) {
            loadPosts();
        }
    }, [clearAgentRunState, loadPosts]);
    
    // Load older messages (prepend)
    const loadMore = useCallback(async () => {
        if (!posts || posts.length === 0) return;
        
        // Find oldest post id
        const sortedPosts = posts.slice().sort((a, b) => a.id - b.id);
        const oldestId = sortedPosts[0].id;
        
        console.log('Loading more before id:', oldestId);
        try {
            const result = await getTimeline(5, oldestId);
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
            const result = await getTimeline(10);
            setPosts(result.posts);
            setHasMore(result.has_more);
        } catch (error) {
            console.error('Failed to load timeline:', error);
        }
    }, []);

    // Handle search
    const handleSearch = useCallback(async (query) => {
        if (!query || !query.trim()) return;
        setSearchQuery(query.trim());
        setCurrentHashtag(null);
        setPosts(null);
        try {
            const result = await searchPosts(query.trim());
            setPosts(result.results);
            setHasMore(false);
        } catch (error) {
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
        const turnId = data?.turn_id;

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
                getAgentContext().then(ctx => { if (ctx && ctx.percent != null) setContextUsage(ctx); }).catch(() => {});
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
            if (turnId && currentTurnIdRef.current && turnId !== currentTurnIdRef.current) {
                return;
            }
            const targetTurn = turnId || currentTurnIdRef.current;
            if (!targetTurn) return;
            steerQueuedTurnIdRef.current = targetTurn;
            setSteerQueuedTurnId(targetTurn);
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
    const isAgentActive = agentStatus !== null;
    useEffect(() => {
        if (connectionStatus !== 'connected') return;
        const intervalMs = isAgentActive ? 15000 : 60000;
        const interval = setInterval(() => {
            if (!isAgentActive) {
                const { currentHashtag: activeHashtag, searchQuery: activeSearch } = viewStateRef.current || {};
                if (!activeHashtag && !activeSearch) {
                    loadPosts();
                }
            }
        }, intervalMs);
        return () => clearInterval(interval);
    }, [connectionStatus, isAgentActive, loadPosts]);

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

    const editorOpen = editorState.open;
    
    return html`
        <div class=${`app-shell${workspaceOpen ? '' : ' workspace-collapsed'}${editorOpen ? ' editor-open' : ''}`} ref=${appShellRef}>
            <${WorkspaceExplorer} onFileSelect=${addFileRef} visible=${workspaceOpen} active=${workspaceOpen || editorOpen} onOpenEditor=${openEditor} renderMarkdown=${renderMarkdown} />
            <button
                class=${`workspace-toggle-tab${workspaceOpen ? ' open' : ' closed'}`}
                onClick=${toggleWorkspace}
                title=${workspaceOpen ? 'Hide workspace' : 'Show workspace'}
                aria-label=${workspaceOpen ? 'Hide workspace' : 'Show workspace'}
            >
                <svg class="workspace-toggle-tab-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <polyline points="6 3 11 8 6 13" />
                </svg>
            </button>
            <div class="workspace-splitter" onMouseDown=${handleSplitterMouseDown} onTouchStart=${handleSplitterTouchStart}></div>
            ${editorOpen && html`
                <${WorkspaceEditor}
                    path=${editorState.path}
                    content=${editorState.content}
                    loading=${editorState.loading}
                    error=${editorState.error}
                    saving=${editorSaving}
                    saveError=${editorSaveError}
                    savedAt=${editorSavedAt}
                    onSave=${handleEditorSave}
                    onClose=${closeEditor}
                />
                <div class="editor-splitter" onMouseDown=${handleEditorSplitterMouseDown} onTouchStart=${handleEditorSplitterTouchStart}></div>
            `}
            <div class="container">
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
                    onPostClick=${undefined}
                    onDeletePost=${handleDeletePost}
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
                <${ComposeBox} 
                    onPost=${() => { loadPosts(); scrollToBottom(); }}
                    onFocus=${scrollToBottom}
                    searchMode=${searchOpen}
                    onSearch=${handleSearch}
                    onEnterSearch=${enterSearchMode}
                    onExitSearch=${exitSearchMode}
                    fileRefs=${fileRefs}
                    onRemoveFileRef=${removeFileRef}
                    onClearFileRefs=${clearFileRefs}
                    activeModel=${activeModel}
                    thinkingLevel=${activeThinkingLevel}
                    supportsThinking=${supportsThinking}
                    contextUsage=${contextUsage}
                    onModelChange=${setActiveModel}
                    onModelStateChange=${applyModelState}
                    notificationsEnabled=${notificationsEnabled}
                    notificationPermission=${notificationPermission}
                    onToggleNotifications=${handleToggleNotifications}
                />
                <${ConnectionStatus} status=${connectionStatus} />
                <${AgentRequestModal} request=${pendingRequest} onRespond=${() => setPendingRequest(null)} />
            </div>
        </div>
    `;
}

// Mount the app
render(html`<${App} />`, document.getElementById('app'));
