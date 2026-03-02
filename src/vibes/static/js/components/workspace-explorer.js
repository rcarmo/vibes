import { html, useEffect, useMemo, useRef, useState } from '../vendor/preact-htm.js';
import {
    attachWorkspaceFile,
    getMediaInfo,
    getMediaUrl,
    getWorkspaceFile,
    getWorkspaceRawUrl,
    getWorkspaceTree,
    setWorkspaceVisibility,
} from '../api.js';

const INDENT = 16;
const REFRESH_INTERVAL_MS = 60_000;

function formatFileSize(bytes) {
    if (!Number.isFinite(bytes)) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTimestamp(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value || '';
    return date.toLocaleString();
}

const isHiddenNode = (node) => {
    if (!node || !node.name) return false;
    if (node.path === '.') return false;
    return node.name.startsWith('.');
};

function flattenTree(node, expanded, showHidden, depth = 0, rows = []) {
    if (!node) return rows;
    if (!showHidden && isHiddenNode(node)) return rows;
    rows.push({ node, depth });
    if (node.type === 'dir' && Array.isArray(node.children) && expanded.has(node.path)) {
        for (const child of node.children) flattenTree(child, expanded, showHidden, depth + 1, rows);
    }
    return rows;
}

function mergeTree(prev, next) {
    if (!next) return prev;
    if (!prev) return next;
    if (prev.path !== next.path || prev.type !== next.type) return next;

    const prevChildren = Array.isArray(prev.children) ? prev.children : [];
    const nextChildren = Array.isArray(next.children) ? next.children : [];
    if (prevChildren.length !== nextChildren.length) return next;

    const prevMap = new Map(prevChildren.map((child) => [child.path, child]));
    let changed = false;
    const mergedChildren = nextChildren.map((child) => {
        const merged = mergeTree(prevMap.get(child.path), child);
        if (merged !== prevMap.get(child.path)) changed = true;
        return merged;
    });
    if (changed) return { ...next, children: mergedChildren };
    return prev;
}

function replaceNodeAtPath(node, targetPath, nextNode) {
    if (!node) return node;
    if (node.path === targetPath) return mergeTree(node, nextNode);
    if (!Array.isArray(node.children)) return node;
    let changed = false;
    const children = node.children.map((child) => {
        const updated = replaceNodeAtPath(child, targetPath, nextNode);
        if (updated !== child) changed = true;
        return updated;
    });
    return changed ? { ...node, children } : node;
}

function FileAttachmentCard({ mediaId }) {
    const [info, setInfo] = useState(null);
    useEffect(() => {
        if (!mediaId) return;
        getMediaInfo(mediaId).then(setInfo).catch(() => {});
    }, [mediaId]);
    if (!info) return null;
    const filename = info.filename || 'file';
    const sizeStr = info.metadata?.size ? formatFileSize(info.metadata.size) : '';
    return html`
        <a href=${getMediaUrl(mediaId)} download=${filename} class="file-attachment" onClick=${(e) => e.stopPropagation()}>
            <svg class="file-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
                <polyline points="10 9 9 9 8 9"/>
            </svg>
            <div class="file-info">
                <span class="file-name">${filename}</span>
                ${sizeStr && html`<span class="file-size">${sizeStr}</span>`}
            </div>
            <svg class="download-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
        </a>
    `;
}

export function WorkspaceExplorer({ onFileSelect, renderMarkdown }) {
    const [tree, setTree] = useState(null);
    const [expanded, setExpanded] = useState(new Set(['.']));
    const [selectedPath, setSelectedPath] = useState(null);
    const [preview, setPreview] = useState(null);
    const [downloadId, setDownloadId] = useState(null);
    const [initialLoad, setInitialLoad] = useState(true);
    const [loadingPreview, setLoadingPreview] = useState(false);
    const [error, setError] = useState(null);
    const [showHidden, setShowHidden] = useState(() => {
        if (typeof window === 'undefined') return false;
        return localStorage.getItem('workspaceShowHidden') === 'true';
    });

    const expandedRef = useRef(expanded);
    const showHiddenRef = useRef(showHidden);
    const nodeMapRef = useRef(new Map());
    const sidebarRef = useRef(null);
    const previewHeightRef = useRef(280);
    const loadTreeRef = useRef(null);
    const loadPreviewRef = useRef(null);
    const loadSubtreeRef = useRef(null);

    useEffect(() => { expandedRef.current = expanded; }, [expanded]);
    useEffect(() => { showHiddenRef.current = showHidden; }, [showHidden]);

    const loadTree = async () => {
        try {
            const data = await getWorkspaceTree('', 4, showHiddenRef.current);
            setTree((prev) => mergeTree(prev, data.root));
            setInitialLoad(false);
            setError(null);
        } catch (err) {
            setError(err?.message || 'Failed to load workspace');
            setInitialLoad(false);
        }
    };
    loadTreeRef.current = loadTree;

    const loadSubtree = async (path) => {
        try {
            const data = await getWorkspaceTree(path, 3, showHiddenRef.current);
            setTree((prev) => replaceNodeAtPath(prev, path, data.root));
        } catch (err) {
            setError(err?.message || 'Failed to load workspace');
        }
    };
    loadSubtreeRef.current = loadSubtree;

    const loadPreview = async (path) => {
        setLoadingPreview(true);
        setPreview(null);
        setDownloadId(null);
        try {
            const data = await getWorkspaceFile(path, 20_000);
            setPreview(data);
        } catch (err) {
            setPreview({ error: err?.message || 'Failed to load preview' });
        } finally {
            setLoadingPreview(false);
        }
    };
    loadPreviewRef.current = loadPreview;

    useEffect(() => {
        if (typeof window === 'undefined') return;
        const handler = (event) => {
            const updates = event?.detail?.updates || [];
            if (!Array.isArray(updates) || updates.length === 0) return;
            setTree((prev) => {
                let next = prev;
                for (const update of updates) {
                    if (!update?.root) continue;
                    if (!next || !update.path || update.path === '.') next = update.root;
                    else next = replaceNodeAtPath(next, update.path, update.root);
                }
                return next;
            });
        };
        window.addEventListener('workspace-update', handler);
        return () => window.removeEventListener('workspace-update', handler);
    }, []);

    const updateVisibility = useRef(() => {
        if (typeof window === 'undefined') return;
        const media = window.matchMedia('(min-width: 1024px) and (orientation: landscape)');
        const visible = media.matches && document.visibilityState !== 'hidden';
        setWorkspaceVisibility(visible, showHiddenRef.current).catch(() => {});
    }).current;

    const visibilityTimerRef = useRef(0);
    const scheduleVisibilityUpdate = useRef(() => {
        if (visibilityTimerRef.current) clearTimeout(visibilityTimerRef.current);
        visibilityTimerRef.current = setTimeout(() => {
            visibilityTimerRef.current = 0;
            updateVisibility();
        }, 250);
    }).current;

    useEffect(() => {
        loadTreeRef.current?.();
        updateVisibility();
        const timer = setInterval(() => loadTreeRef.current?.(), REFRESH_INTERVAL_MS);

        const saved = parseInt(localStorage.getItem('previewHeight') || '', 10);
        const h = Number.isFinite(saved) ? Math.min(Math.max(saved, 80), 600) : 280;
        previewHeightRef.current = h;
        if (sidebarRef.current) {
            sidebarRef.current.style.setProperty('--preview-height', `${h}px`);
        }

        const media = window.matchMedia('(min-width: 1024px) and (orientation: landscape)');
        const onVisibilityChange = () => scheduleVisibilityUpdate();
        if (media.addEventListener) media.addEventListener('change', onVisibilityChange);
        else if (media.addListener) media.addListener(onVisibilityChange);
        document.addEventListener('visibilitychange', onVisibilityChange);

        return () => {
            clearInterval(timer);
            if (media.removeEventListener) media.removeEventListener('change', onVisibilityChange);
            else if (media.removeListener) media.removeListener(onVisibilityChange);
            document.removeEventListener('visibilitychange', onVisibilityChange);
            if (visibilityTimerRef.current) clearTimeout(visibilityTimerRef.current);
            setWorkspaceVisibility(false, showHiddenRef.current).catch(() => {});
        };
    }, []);

    const rows = useMemo(() => flattenTree(tree, expanded, showHidden), [tree, expanded, showHidden]);
    const nodeMap = useMemo(() => new Map(rows.map((row) => [row.node.path, row.node])), [rows]);
    nodeMapRef.current = nodeMap;

    const handleTreeClick = useRef((e) => {
        const rowEl = e.target.closest('[data-path]');
        if (!rowEl) return;
        const path = rowEl.dataset.path;
        const type = rowEl.dataset.type;
        if (type === 'dir') {
            const isOpen = expandedRef.current.has(path);
            if (!isOpen) loadSubtreeRef.current?.(path);
            setExpanded((prev) => {
                const next = new Set(prev);
                if (next.has(path)) next.delete(path);
                else next.add(path);
                return next;
            });
            return;
        }
        setSelectedPath(path);
        const node = nodeMapRef.current.get(path);
        onFileSelect?.(node?.path || path, node || null);
        loadPreviewRef.current?.(path);
    }).current;

    const handleRefresh = useRef(() => {
        loadTreeRef.current?.();
        const openPaths = Array.from(expandedRef.current || []).filter((p) => p && p !== '.');
        openPaths.forEach((p) => loadSubtreeRef.current?.(p));
    }).current;

    const clearSelection = useRef(() => {
        setSelectedPath(null);
        setPreview(null);
        setDownloadId(null);
        setLoadingPreview(false);
    }).current;

    const handleToggleHidden = useRef(() => {
        setShowHidden((prev) => {
            const next = !prev;
            if (typeof window !== 'undefined') {
                localStorage.setItem('workspaceShowHidden', String(next));
            }
            showHiddenRef.current = next;
            setWorkspaceVisibility(true, next).catch(() => {});
            loadTreeRef.current?.();
            const openPaths = Array.from(expandedRef.current || []).filter((p) => p && p !== '.');
            openPaths.forEach((p) => loadSubtreeRef.current?.(p));
            return next;
        });
    }).current;

    const handleBackgroundClick = useRef((e) => {
        if (e.target.closest('[data-path]')) return;
        clearSelection();
    }).current;

    const handlePreviewSplitterMouseDown = useRef((e) => {
        e.preventDefault();
        const sidebar = sidebarRef.current;
        if (!sidebar) return;
        const startY = e.clientY;
        const startH = previewHeightRef.current || 280;
        const splitter = e.currentTarget;
        splitter.classList.add('dragging');
        document.body.style.cursor = 'row-resize';
        document.body.style.userSelect = 'none';

        let lastY = startY;
        const onMove = (event) => {
            lastY = event.clientY;
            const maxH = sidebar.clientHeight - 80;
            const h = Math.min(Math.max(startH - (event.clientY - startY), 80), maxH);
            sidebar.style.setProperty('--preview-height', `${h}px`);
            previewHeightRef.current = h;
        };
        const onUp = () => {
            const maxH = sidebar.clientHeight - 80;
            const h = Math.min(Math.max(startH - (lastY - startY), 80), maxH);
            previewHeightRef.current = h;
            splitter.classList.remove('dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            localStorage.setItem('previewHeight', String(Math.round(h)));
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    }).current;

    const handlePreviewSplitterTouchStart = useRef((e) => {
        e.preventDefault();
        const sidebar = sidebarRef.current;
        if (!sidebar) return;
        const touch = e.touches[0];
        if (!touch) return;
        const startY = touch.clientY;
        const startH = previewHeightRef.current || 280;
        const splitter = e.currentTarget;
        splitter.classList.add('dragging');
        document.body.style.userSelect = 'none';

        const onMove = (event) => {
            const t = event.touches[0];
            if (!t) return;
            event.preventDefault();
            const maxH = sidebar.clientHeight - 80;
            const h = Math.min(Math.max(startH - (t.clientY - startY), 80), maxH);
            sidebar.style.setProperty('--preview-height', `${h}px`);
            previewHeightRef.current = h;
        };
        const onUp = () => {
            splitter.classList.remove('dragging');
            document.body.style.userSelect = '';
            localStorage.setItem('previewHeight', String(Math.round(previewHeightRef.current || startH)));
            document.removeEventListener('touchmove', onMove);
            document.removeEventListener('touchend', onUp);
            document.removeEventListener('touchcancel', onUp);
        };
        document.addEventListener('touchmove', onMove, { passive: false });
        document.addEventListener('touchend', onUp);
        document.addEventListener('touchcancel', onUp);
    }).current;

    const handleDownload = async () => {
        if (!selectedPath) return;
        try {
            const result = await attachWorkspaceFile(selectedPath);
            if (result?.media_id) setDownloadId(result.media_id);
        } catch (err) {
            setPreview((prev) => ({ ...(prev || {}), error: err?.message || 'Failed to attach' }));
        }
    };

    const renderPreviewMarkdown = renderMarkdown || ((value) => value || '');

    return html`
        <aside class="workspace-sidebar" ref=${sidebarRef}>
            <div class="workspace-header">
                <span>Workspace</span>
                <div class="workspace-header-actions">
                    <button class="workspace-refresh" onClick=${handleRefresh} title="Refresh">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                            <circle cx="12" cy="12" r="8.5" stroke-dasharray="42 12" stroke-dashoffset="6" transform="rotate(75 12 12)" />
                            <polyline points="21 3 21 9 15 9" />
                        </svg>
                    </button>
                    <button
                        class=${`workspace-toggle-hidden${showHidden ? ' active' : ''}`}
                        onClick=${handleToggleHidden}
                        title=${showHidden ? 'Hide hidden files' : 'Show hidden files'}
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                            <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" />
                            <circle cx="12" cy="12" r="3" />
                            ${!showHidden && html`<line x1="3" y1="3" x2="21" y2="21" />`}
                        </svg>
                    </button>
                </div>
            </div>
            <div class="workspace-tree" onClick=${handleBackgroundClick}>
                ${initialLoad && html`<div class="workspace-loading">Loading…</div>`}
                ${error && html`<div class="workspace-error">${error}</div>`}
                ${tree && html`
                    <div class="workspace-tree-list" onClick=${handleTreeClick}>
                        ${rows.map(({ node, depth }) => {
                            const isDir = node.type === 'dir';
                            const isSelected = node.path === selectedPath;
                            const isOpen = isDir && expanded.has(node.path);
                            return html`
                                <div
                                    key=${node.path}
                                    class=${`workspace-row${isSelected ? ' selected' : ''}`}
                                    style=${{ paddingLeft: `${8 + depth * INDENT}px` }}
                                    data-path=${node.path}
                                    data-type=${node.type}
                                >
                                    <span class="workspace-caret" aria-hidden="true">
                                        ${isDir
                                            ? (isOpen
                                                ? html`<svg viewBox="0 0 12 12"><polygon points="1,2 11,2 6,11"/></svg>`
                                                : html`<svg viewBox="0 0 12 12"><polygon points="2,1 11,6 2,11"/></svg>`)
                                            : null}
                                    </span>
                                    <svg class=${`workspace-node-icon${isDir ? ' folder' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                        ${isDir
                                            ? html`<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>`
                                            : html`<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>`}
                                    </svg>
                                    <span class="workspace-label">${node.name}</span>
                                </div>
                            `;
                        })}
                    </div>
                `}
            </div>
            ${selectedPath && html`
                <div class="workspace-preview-splitter-h" onMouseDown=${handlePreviewSplitterMouseDown} onTouchStart=${handlePreviewSplitterTouchStart}></div>
                <div class="workspace-preview">
                    <div class="workspace-preview-header">
                        <span class="workspace-preview-title">${selectedPath}</span>
                        <button class="workspace-download" onClick=${handleDownload} title="Download">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                                <polyline points="7 10 12 15 17 10"/>
                                <line x1="12" y1="15" x2="12" y2="3"/>
                            </svg>
                        </button>
                    </div>
                    ${loadingPreview && html`<div class="workspace-loading">Loading preview…</div>`}
                    ${preview?.error && html`<div class="workspace-error">${preview.error}</div>`}
                    ${preview && !preview.error && html`
                        <div class="workspace-preview-meta">
                            ${preview.size ? html`<span>${formatFileSize(preview.size)}</span>` : ''}
                            ${preview.mtime ? html`<span>${formatTimestamp(preview.mtime)}</span>` : ''}
                            ${preview.truncated ? html`<span>truncated</span>` : ''}
                        </div>
                        ${preview.kind === 'image' && html`
                            <div class="workspace-preview-image">
                                <img src=${preview.url || getWorkspaceRawUrl(preview.path)} alt="preview" />
                            </div>
                        `}
                        ${preview.kind === 'text' && html`
                            ${preview.content_type === 'text/markdown'
                                ? html`<div class="workspace-preview-text" dangerouslySetInnerHTML=${{ __html: renderPreviewMarkdown(preview.text || '') }} />`
                                : html`<pre class="workspace-preview-text"><code>${preview.text || ''}</code></pre>`}
                        `}
                        ${preview.kind === 'binary' && html`
                            <div class="workspace-preview-text">Binary file — download to view.</div>
                        `}
                    `}
                    ${downloadId && html`
                        <div class="workspace-download-card">
                            <${FileAttachmentCard} mediaId=${downloadId} />
                        </div>
                    `}
                </div>
            `}
        </aside>
    `;
}
