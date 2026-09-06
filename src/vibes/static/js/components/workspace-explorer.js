import { html, useCallback, useEffect, useMemo, useRef, useState } from '../vendor/preact-htm.js';
import {
    attachWorkspaceFile,
    createWorkspaceFile,
    deleteWorkspaceFile,
    getMediaInfo,
    getMediaUrl,
    getWorkspaceDownloadUrl,
    getWorkspaceFile,
    getWorkspaceRawUrl,
    getWorkspaceTree,
    moveWorkspaceEntry,
    renameWorkspaceFile,
    setWorkspaceVisibility,
    uploadWorkspaceFile,
} from '../api.js';
import { DiskUsageSunburst } from './sunburst.js';

const INDENT = 16;
const REFRESH_INTERVAL_MS = 60_000;

/**
 * Rewrite relative src/href attributes in rendered HTML so images and links
 * inside markdown previews resolve against the workspace raw endpoint.
 */
function rewriteRelativeUrls(htmlStr, filePath) {
    if (!filePath) return htmlStr;
    const dir = filePath.includes('/') ? filePath.slice(0, filePath.lastIndexOf('/')) : '.';
    return htmlStr.replace(
        /(<(?:img|source)\s[^>]*?\bsrc\s*=\s*["'])([^"']+)(["'])/gi,
        (match, pre, url, post) => {
            if (/^(?:https?:|data:|\/)/i.test(url)) return match;
            const clean = url.replace(/^\.\//, '');
            const resolved = dir === '.' ? clean : `${dir}/${clean}`;
            return `${pre}${getWorkspaceRawUrl(resolved)}${post}`;
        }
    );
}

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

/**
 * Signature of *visible* structure only: path + type for expanded nodes.
 */
function treeSignature(node, expanded, showHidden) {
    if (!node) return '';
    const parts = [];
    const walk = (item) => {
        if (!item) return;
        if (!showHidden && isHiddenNode(item)) return;
        parts.push(item.path, item.type);
        if (item.children && expanded?.has(item.path)) {
            for (const child of item.children) walk(child);
        }
    };
    walk(node);
    return parts.join('|');
}

function mergeTree(prev, next) {
    if (!next) return null;
    if (!prev) return next;
    if (prev.path !== next.path || prev.type !== next.type) return next;

    const prevKids = Array.isArray(prev.children) ? prev.children : null;
    const nextKids = Array.isArray(next.children) ? next.children : null;

    // Server hit depth limit and returned no children – keep what we had.
    if (!nextKids) return prev;

    const prevMap = prevKids ? new Map(prevKids.map((c) => [c?.path, c])) : new Map();
    let changed = !prevKids || prevKids.length !== nextKids.length;
    const merged = nextKids.map((child) => {
        const m = mergeTree(prevMap.get(child.path), child);
        if (m !== prevMap.get(child.path)) changed = true;
        return m;
    });
    return changed ? { ...next, children: merged } : prev;
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

export function WorkspaceExplorer({ onFileSelect, onFolderSelect, visible = true, active = undefined, onOpenEditor, renderMarkdown }) {
    const [tree, setTree] = useState(null);
    const [expanded, setExpanded] = useState(new Set(['.']));
    const [selectedPath, setSelectedPath] = useState(null);
    const [renamingPath, setRenamingPath] = useState(null);
    const [renameValue, setRenameValue] = useState('');
    const [preview, setPreview] = useState(null);
    const [downloadId, setDownloadId] = useState(null);
    const [initialLoad, setInitialLoad] = useState(true);
    const [loadingPreview, setLoadingPreview] = useState(false);
    const [error, setError] = useState(null);
    const [dragActive, setDragActive] = useState(false);
    const [dragMode, setDragMode] = useState(null);
    const [dropTarget, setDropTarget] = useState(null);
    const [uploading, setUploading] = useState(false);
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
    const pendingSubtreeRef = useRef(new Set());
    const lastSigRef = useRef('');
    const pendingRootRef = useRef(null);
    const rafRef = useRef(0);
    const dragDepthRef = useRef(0);
    const dropTargetRef = useRef(dropTarget);
    const dragActiveRef = useRef(dragActive);
    const dragModeRef = useRef(dragMode);
    const visibleRef = useRef(visible);
    const activeRef = useRef(active ?? visible);
    const selectedPathRef = useRef(selectedPath);
    const renamingPathRef = useRef(renamingPath);
    const renameInputRef = useRef(null);
    const folderUploadRef = useRef(null);
    const folderUploadTargetRef = useRef('.');
    const treeListRef = useRef(null);
    const longPressTimerRef = useRef(null);
    const touchDragRef = useRef({ path: null, dragging: false, startX: 0, startY: 0 });
    const moveEntryToTargetRef = useRef(null);

    useEffect(() => { expandedRef.current = expanded; }, [expanded]);
    useEffect(() => { showHiddenRef.current = showHidden; }, [showHidden]);
    useEffect(() => { dropTargetRef.current = dropTarget; }, [dropTarget]);
    useEffect(() => { dragActiveRef.current = dragActive; }, [dragActive]);
    useEffect(() => { dragModeRef.current = dragMode; }, [dragMode]);
    useEffect(() => { visibleRef.current = visible; }, [visible]);
    useEffect(() => { activeRef.current = active ?? visible; }, [active, visible]);
    useEffect(() => { selectedPathRef.current = selectedPath; }, [selectedPath]);
    useEffect(() => { renamingPathRef.current = renamingPath; }, [renamingPath]);

    useEffect(() => {
        if (!renamingPath) return;
        const input = renameInputRef.current;
        if (!input) return;
        const timer = requestAnimationFrame(() => {
            try { input.focus(); input.select(); } catch {}
        });
        return () => cancelAnimationFrame(timer);
    }, [renamingPath]);

    const resolveDropTargetFromElement = useCallback((element) => {
        const row = element?.closest?.('.workspace-row');
        if (!row) return null;
        const path = row.dataset.path;
        const type = row.dataset.type;
        if (!path) return null;
        if (type === 'dir') return path;
        if (path.includes('/')) {
            const parts = path.split('/');
            parts.pop();
            return parts.join('/') || '.';
        }
        return '.';
    }, []);

    const resolveDropTargetFromEvent = useCallback((event) => {
        return resolveDropTargetFromElement(event?.target || null);
    }, [resolveDropTargetFromElement]);

    const resolveCreateTargetPath = useCallback((path) => {
        if (!path) return '.';
        const node = nodeMapRef.current?.get(path);
        if (node && node.type === 'dir') return node.path;
        if (path === '.' || !path.includes('/')) return '.';
        const parts = path.split('/');
        parts.pop();
        return parts.join('/') || '.';
    }, []);

    const resolveDropTargetPath = useCallback(() => {
        const sel = selectedPathRef.current;
        if (!sel) return '.';
        const node = nodeMapRef.current?.get(sel);
        if (node && node.type === 'dir') return node.path;
        if (sel === '.' || !sel.includes('/')) return '.';
        const parts = sel.split('/');
        parts.pop();
        return parts.join('/') || '.';
    }, []);

    const cancelRename = useCallback(() => {
        setRenamingPath(null);
        setRenameValue('');
    }, []);

    const beginRename = useCallback((path) => {
        if (!path) return;
        const node = nodeMapRef.current?.get(path);
        const base = (node?.name || path.split('/').pop() || path).trim();
        if (!base || path === '.') return;
        setRenamingPath(path);
        setRenameValue(base);
    }, []);

    const commitRename = useCallback(async () => {
        const targetPath = renamingPathRef.current;
        if (!targetPath) return;
        const nextName = (renameValue || '').trim();
        if (!nextName) { cancelRename(); return; }

        const node = nodeMapRef.current?.get(targetPath);
        const currentName = (node?.name || targetPath.split('/').pop() || targetPath).trim();
        if (nextName === currentName) { cancelRename(); return; }

        try {
            const result = await renameWorkspaceFile(targetPath, nextName);
            const nextPath = result?.path || targetPath;
            const parent = targetPath.includes('/')
                ? (targetPath.split('/').slice(0, -1).join('/') || '.') : '.';
            cancelRename();
            setError(null);
            if (node?.type === 'dir') {
                setExpanded((prev) => {
                    const next = new Set();
                    for (const entry of prev) {
                        if (entry === targetPath) next.add(nextPath);
                        else if (entry.startsWith(`${targetPath}/`)) next.add(`${nextPath}${entry.slice(targetPath.length)}`);
                        else next.add(entry);
                    }
                    return next;
                });
            }
            setSelectedPath(nextPath);
            if (node?.type === 'dir') { setPreview(null); setLoadingPreview(false); setDownloadId(null); }
            else { loadPreviewRef.current?.(nextPath); }
            loadSubtreeRef.current?.(parent);
        } catch (err) {
            setError(err?.message || 'Failed to rename file');
        }
    }, [cancelRename, renameValue]);

    const createUntitledFile = useCallback(async (targetPath) => {
        const folder = targetPath || '.';
        for (let i = 0; i < 50; i += 1) {
            const suffix = i === 0 ? '' : `-${i}`;
            const name = `untitled${suffix}.md`;
            try {
                const result = await createWorkspaceFile(folder, name, '');
                const nextPath = result?.path || (folder === '.' ? name : `${folder}/${name}`);
                if (folder && folder !== '.') setExpanded((prev) => new Set([...prev, folder]));
                setSelectedPath(nextPath);
                setError(null);
                loadSubtreeRef.current?.(folder);
                loadPreviewRef.current?.(nextPath);
                return;
            } catch (err) {
                if (err?.message?.includes?.('already exists')) continue;
                setError(err?.message || 'Failed to create file');
                return;
            }
        }
        setError('Failed to create file (untitled name already in use).');
    }, []);

    const handleCreateFileClick = useCallback((event) => {
        event?.stopPropagation?.();
        if (uploading) return;
        const target = resolveCreateTargetPath(selectedPathRef.current);
        createUntitledFile(target);
    }, [uploading, resolveCreateTargetPath, createUntitledFile]);

    const moveEntryToTarget = useCallback(async (sourcePath, targetPath) => {
        if (!sourcePath) return;
        const node = nodeMapRef.current?.get(sourcePath);
        if (!node) return;
        const targetDir = targetPath && targetPath !== '' ? targetPath : '.';
        const sourceParent = sourcePath.includes('/')
            ? (sourcePath.split('/').slice(0, -1).join('/') || '.') : '.';
        if (targetDir === sourceParent) return;
        try {
            const result = await moveWorkspaceEntry(sourcePath, targetDir);
            const nextPath = result?.path || sourcePath;
            if (node.type === 'dir') {
                setExpanded((prev) => {
                    const next = new Set();
                    for (const entry of prev) {
                        if (entry === sourcePath) next.add(nextPath);
                        else if (entry.startsWith(`${sourcePath}/`)) next.add(`${nextPath}${entry.slice(sourcePath.length)}`);
                        else next.add(entry);
                    }
                    return next;
                });
            }
            setSelectedPath(nextPath);
            if (node.type === 'dir') { setPreview(null); setLoadingPreview(false); setDownloadId(null); }
            else { loadPreviewRef.current?.(nextPath); }
            loadSubtreeRef.current?.(sourceParent);
            loadSubtreeRef.current?.(targetDir);
        } catch (err) {
            setError(err?.message || 'Failed to move entry');
        }
    }, []);
    moveEntryToTargetRef.current = moveEntryToTarget;

    const loadTree = async () => {
        if (!activeRef.current) return;
        try {
            const data = await getWorkspaceTree('', 2, showHiddenRef.current);
            const sig = treeSignature(data.root, expandedRef.current, showHiddenRef.current);
            if (sig === lastSigRef.current) {
                setInitialLoad(false);
                return;
            }
            lastSigRef.current = sig;
            pendingRootRef.current = data.root;
            if (!rafRef.current) {
                rafRef.current = requestAnimationFrame(() => {
                    rafRef.current = 0;
                    setTree((prev) => mergeTree(prev, pendingRootRef.current));
                    setInitialLoad(false);
                });
            }
            setError(null);
        } catch (err) {
            setError(err?.message || 'Failed to load workspace');
            setInitialLoad(false);
        }
    };
    loadTreeRef.current = loadTree;

    const loadSubtree = async (path) => {
        if (!path) return;
        if (pendingSubtreeRef.current.has(path)) return;
        pendingSubtreeRef.current.add(path);
        try {
            const data = await getWorkspaceTree(path, 1, showHiddenRef.current);
            setTree((prev) => replaceNodeAtPath(prev, path, data.root));
        } catch (err) {
            setError(err?.message || 'Failed to load workspace');
        } finally {
            pendingSubtreeRef.current.delete(path);
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
                    if (!next || !update.path || update.path === '.') next = mergeTree(next, update.root);
                    else next = replaceNodeAtPath(next, update.path, update.root);
                }
                if (next) {
                    lastSigRef.current = treeSignature(next, expandedRef.current, showHiddenRef.current);
                }
                setInitialLoad(false);
                return next;
            });
            // Re-fetch preview if the selected file's parent was updated
            const sel = selectedPathRef.current;
            if (sel && loadPreviewRef.current) {
                const selParent = sel.includes('/') ? sel.slice(0, sel.lastIndexOf('/')) : '.';
                const affected = updates.some(u =>
                    u?.path === '.' || u?.path === selParent || sel.startsWith((u?.path || '') + '/')
                );
                if (affected) loadPreviewRef.current(sel);
            }
        };
        window.addEventListener('workspace-update', handler);
        return () => window.removeEventListener('workspace-update', handler);
    }, []);

    const updateVisibility = useRef(() => {
        if (typeof window === 'undefined') return;
        const media = window.matchMedia('(min-width: 1024px) and (orientation: landscape)');
        const shouldBeActive = activeRef.current ?? visibleRef.current;
        const visible = media.matches && document.visibilityState !== 'hidden' && shouldBeActive;
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
        if (activeRef.current) {
            loadTreeRef.current?.();
        }
        scheduleVisibilityUpdate();
    }, [visible, active]);

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
    const selectedNode = selectedPath ? nodeMapRef.current.get(selectedPath) : null;
    const selectedIsDir = selectedNode?.type === 'dir';

    const handleTreeClick = useRef((e) => {
        const rowEl = e.target.closest('[data-path]');
        if (!rowEl) return;
        const path = rowEl.dataset.path;
        const type = rowEl.dataset.type;
        const isCaretClick = Boolean(e.target.closest('.workspace-caret'));
        const isActionClick = Boolean(e.target.closest('button')) || Boolean(e.target.closest('a')) || Boolean(e.target.closest('input'));
        const isSelected = selectedPathRef.current === path;
        const renaming = renamingPathRef.current;

        if (renaming) {
            if (renaming === path) return;
            cancelRename();
        }

        if (isSelected && !isCaretClick && !isActionClick && path !== '.') {
            beginRename(path);
            return;
        }

        if (type === 'dir') {
            onFolderSelect?.(path);
            setSelectedPath(path);
            setPreview(null);
            setDownloadId(null);
            setLoadingPreview(false);
            const wasExpanded = expandedRef.current.has(path);
            if (!wasExpanded) loadSubtreeRef.current?.(path);
            if (isSelected && !isCaretClick) return;
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
        lastSigRef.current = '';
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
            lastSigRef.current = '';
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

    const handleTreeKeyDown = useCallback((e) => {
        const currentRows = rows;
        if (!currentRows || currentRows.length === 0) return;
        const curIdx = selectedPath
            ? currentRows.findIndex((r) => r.node.path === selectedPath)
            : -1;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            const next = Math.min(curIdx + 1, currentRows.length - 1);
            const row = currentRows[next];
            setSelectedPath(row.node.path);
            if (row.node.type !== 'dir') loadPreviewRef.current?.(row.node.path);
            else { setPreview(null); setLoadingPreview(false); }
            scrollRowIntoView(row.node.path);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            const next = curIdx <= 0 ? 0 : curIdx - 1;
            const row = currentRows[next];
            setSelectedPath(row.node.path);
            if (row.node.type !== 'dir') loadPreviewRef.current?.(row.node.path);
            else { setPreview(null); setLoadingPreview(false); }
            scrollRowIntoView(row.node.path);
        } else if (e.key === 'ArrowRight' && curIdx >= 0) {
            const row = currentRows[curIdx];
            if (row.node.type === 'dir' && !expanded.has(row.node.path)) {
                e.preventDefault();
                loadSubtreeRef.current?.(row.node.path);
                setExpanded((prev) => new Set([...prev, row.node.path]));
            }
        } else if (e.key === 'ArrowLeft' && curIdx >= 0) {
            const row = currentRows[curIdx];
            if (row.node.type === 'dir' && expanded.has(row.node.path)) {
                e.preventDefault();
                setExpanded((prev) => { const next = new Set(prev); next.delete(row.node.path); return next; });
            }
        } else if (e.key === 'Enter' && curIdx >= 0) {
            e.preventDefault();
            const row = currentRows[curIdx];
            if (row.node.type === 'dir') {
                loadSubtreeRef.current?.(row.node.path);
                setExpanded((prev) => {
                    const next = new Set(prev);
                    if (next.has(row.node.path)) next.delete(row.node.path);
                    else next.add(row.node.path);
                    return next;
                });
            } else if (onOpenEditor && preview?.kind === 'text') {
                onOpenEditor(row.node.path);
            }
        } else if ((e.key === 'Delete' || e.key === 'Backspace') && curIdx >= 0) {
            const row = currentRows[curIdx];
            if (row.node.type !== 'dir') {
                e.preventDefault();
                handleDeleteFile();
            }
        } else if (e.key === 'Escape') {
            e.preventDefault();
            clearSelection();
        }
    }, [rows, selectedPath, expanded, preview, onOpenEditor]);

    const scrollRowIntoView = useCallback((path) => {
        const container = treeListRef.current;
        if (!container) return;
        const el = container.querySelector(`[data-path="${CSS.escape(path)}"]`);
        el?.scrollIntoView({ block: 'nearest' });
    }, []);

    const deleteFileAtPath = useCallback((path) => {
        const node = nodeMapRef.current.get(path);
        if (node && node.type !== 'dir') {
            const filename = path.split('/').pop() || path;
            if (confirm(`Delete "${filename}"? This cannot be undone.`)) {
                deleteWorkspaceFile(path).then(() => {
                    const parent = path.includes('/') ? (path.split('/').slice(0, -1).join('/') || '.') : '.';
                    clearSelection();
                    loadSubtreeRef.current?.(parent);
                }).catch((err) => {
                    setPreview((prev) => ({ ...(prev || {}), error: err?.message || 'Failed to delete file' }));
                });
            }
        }
    }, []);

    const handleRowTouchStart = useCallback((e) => {
        const rowEl = e.target.closest('[data-path]');
        if (!rowEl) return;
        const path = rowEl.dataset.path;
        const type = rowEl.dataset.type;
        if (!path || path === '.') return;
        if (renamingPathRef.current === path) return;
        const touch = e?.touches?.[0];
        if (!touch) return;

        touchDragRef.current = {
            path, dragging: false,
            startX: touch.clientX, startY: touch.clientY,
        };

        if (type !== 'file') return;
        if (longPressTimerRef.current) clearTimeout(longPressTimerRef.current);
        longPressTimerRef.current = setTimeout(() => {
            longPressTimerRef.current = null;
            if (touchDragRef.current?.dragging) return;
            deleteFileAtPath(path);
        }, 600);
    }, [deleteFileAtPath]);

    const handleRowTouchEnd = useCallback(() => {
        if (longPressTimerRef.current) {
            clearTimeout(longPressTimerRef.current);
            longPressTimerRef.current = null;
        }

        const dragState = touchDragRef.current;
        if (dragState?.dragging && dragState.path) {
            const target = dropTargetRef.current || resolveDropTargetPath();
            const mover = moveEntryToTargetRef.current;
            if (typeof mover === 'function') mover(dragState.path, target);
        }

        touchDragRef.current = { path: null, dragging: false, startX: 0, startY: 0 };
        dragDepthRef.current = 0;
        setDragActive(false);
        setDragMode(null);
        setDropTarget(null);
    }, [resolveDropTargetPath]);

    const handleRowTouchMove = useCallback((event) => {
        const dragState = touchDragRef.current;
        const touch = event?.touches?.[0];
        if (!touch || !dragState?.path) {
            if (longPressTimerRef.current) {
                clearTimeout(longPressTimerRef.current);
                longPressTimerRef.current = null;
            }
            return;
        }

        const dx = Math.abs(touch.clientX - dragState.startX);
        const dy = Math.abs(touch.clientY - dragState.startY);
        const moved = dx > 8 || dy > 8;

        if (moved && longPressTimerRef.current) {
            clearTimeout(longPressTimerRef.current);
            longPressTimerRef.current = null;
        }

        if (!dragState.dragging && moved) {
            dragState.dragging = true;
            setDragActive(true);
            setDragMode('move');
        }

        if (dragState.dragging) {
            event.preventDefault();
            const el = document.elementFromPoint(touch.clientX, touch.clientY);
            const target = resolveDropTargetFromElement(el) || resolveDropTargetPath();
            if (dropTargetRef.current !== target) setDropTarget(target);
        }
    }, [resolveDropTargetFromElement, resolveDropTargetPath]);

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

    const handleDeleteFile = async () => {
        if (!selectedPath || selectedIsDir) return;
        const filename = selectedPath.split('/').pop() || selectedPath;
        const confirmed = window.confirm(`Delete "${filename}"? This cannot be undone.`);
        if (!confirmed) return;
        try {
            await deleteWorkspaceFile(selectedPath);
            const parent = selectedPath.includes('/') ? (selectedPath.split('/').slice(0, -1).join('/') || '.') : '.';
            clearSelection();
            loadSubtreeRef.current?.(parent);
            setError(null);
        } catch (err) {
            setPreview((prev) => ({ ...(prev || {}), error: err?.message || 'Failed to delete file' }));
        }
    };

    const handleFolderUploadClick = useCallback((e) => {
        e.stopPropagation();
        const path = e.currentTarget.dataset.uploadTarget || '.';
        folderUploadTargetRef.current = path;
        folderUploadRef.current?.click();
    }, []);

    const handleFolderUploadChange = useCallback(async (e) => {
        const files = Array.from(e.target.files || []);
        e.target.value = '';
        if (files.length === 0) return;
        const target = folderUploadTargetRef.current;
        setUploading(true);
        try {
            let lastResult = null;
            for (const file of files) {
                try {
                    lastResult = await uploadWorkspaceFile(file, target);
                } catch (err) {
                    if (err?.status === 409 || err?.code === 'file_exists') {
                        const name = file?.name || 'file';
                        const targetLabel = target === '.' ? 'workspace root' : target;
                        if (!confirm(`"${name}" already exists in ${targetLabel}. Overwrite?`)) continue;
                        lastResult = await uploadWorkspaceFile(file, target, { overwrite: true });
                    } else {
                        throw err;
                    }
                }
            }
            if (lastResult?.path) {
                setSelectedPath(lastResult.path);
                loadPreviewRef.current?.(lastResult.path);
            }
            loadSubtreeRef.current?.(target);
        } catch (err) {
            setError(err?.message || 'Failed to upload file');
        } finally {
            setUploading(false);
        }
    }, []);

    const renderPreviewMarkdown = renderMarkdown || ((value) => value || '');

    const isFileDrag = (event) => {
        const types = Array.from(event?.dataTransfer?.types || []);
        return types.includes('Files');
    };

    const isWorkspaceDrag = (event) => {
        const types = Array.from(event?.dataTransfer?.types || []);
        return types.includes('text/x-workspace-path');
    };

    const getWorkspaceDragPath = (event) => {
        const dt = event?.dataTransfer;
        if (!dt) return '';
        return dt.getData('text/x-workspace-path') || dt.getData('text/plain') || '';
    };

    const handleDragEnter = useCallback((event) => {
        const fileDrag = isFileDrag(event);
        const workspaceDrag = isWorkspaceDrag(event);
        if (!fileDrag && !workspaceDrag) return;
        event.preventDefault();
        dragDepthRef.current += 1;
        if (!dragActiveRef.current) setDragActive(true);
        setDragMode(fileDrag ? 'upload' : 'move');
        const target = resolveDropTargetFromEvent(event) || resolveDropTargetPath();
        setDropTarget(target);
    }, [resolveDropTargetPath, resolveDropTargetFromEvent]);

    const handleDragOver = useCallback((event) => {
        const fileDrag = isFileDrag(event);
        const workspaceDrag = isWorkspaceDrag(event);
        if (!fileDrag && !workspaceDrag) return;
        event.preventDefault();
        if (event.dataTransfer) event.dataTransfer.dropEffect = fileDrag ? 'copy' : 'move';
        if (!dragActiveRef.current) setDragActive(true);
        if (dragModeRef.current !== (fileDrag ? 'upload' : 'move')) {
            setDragMode(fileDrag ? 'upload' : 'move');
        }
        const target = resolveDropTargetFromEvent(event) || resolveDropTargetPath();
        if (dropTargetRef.current !== target) setDropTarget(target);
    }, [resolveDropTargetPath, resolveDropTargetFromEvent]);

    const handleDragLeave = useCallback((event) => {
        if (!isFileDrag(event) && !isWorkspaceDrag(event)) return;
        event.preventDefault();
        dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
        if (dragDepthRef.current === 0) {
            setDragActive(false);
            setDragMode(null);
            setDropTarget(null);
        }
    }, []);

    const uploadFilesToTarget = useCallback(async (files, target) => {
        setUploading(true);
        try {
            let lastResult = null;
            for (const file of files) {
                try {
                    lastResult = await uploadWorkspaceFile(file, target);
                } catch (err) {
                    if (err?.status === 409 || err?.code === 'file_exists') {
                        const name = file?.name || 'file';
                        const targetLabel = target === '.' ? 'workspace root' : target;
                        if (!confirm(`"${name}" already exists in ${targetLabel}. Overwrite?`)) continue;
                        lastResult = await uploadWorkspaceFile(file, target, { overwrite: true });
                    } else {
                        throw err;
                    }
                }
            }
            if (lastResult?.path) {
                setSelectedPath(lastResult.path);
                loadPreviewRef.current?.(lastResult.path);
            }
            loadSubtreeRef.current?.(target);
        } catch (err) {
            setError(err?.message || 'Failed to upload file');
        } finally {
            setUploading(false);
        }
    }, []);

    const handleDrop = useCallback(async (event) => {
        const fileDrag = isFileDrag(event);
        const workspaceDrag = isWorkspaceDrag(event);
        if (!fileDrag && !workspaceDrag) return;
        event.preventDefault();
        dragDepthRef.current = 0;
        setDragActive(false);
        setDragMode(null);
        setDropTarget(null);

        if (fileDrag) {
            const files = Array.from(event?.dataTransfer?.files || []);
            if (files.length === 0) return;
            const target = dropTargetRef.current || resolveDropTargetFromEvent(event) || resolveDropTargetPath();
            await uploadFilesToTarget(files, target);
            return;
        }

        const sourcePath = getWorkspaceDragPath(event);
        const target = dropTargetRef.current || resolveDropTargetFromEvent(event) || resolveDropTargetPath();
        if (!sourcePath || !target) return;
        await moveEntryToTarget(sourcePath, target);
    }, [resolveDropTargetPath, resolveDropTargetFromEvent, uploadFilesToTarget, moveEntryToTarget]);

    const handleRowDragStart = useCallback((event) => {
        const rowEl = event?.currentTarget;
        if (!rowEl || !rowEl.dataset) return;
        const path = rowEl.dataset.path;
        if (!path || path === '.') return;
        if (renamingPathRef.current === path) return;
        if (event.dataTransfer) {
            event.dataTransfer.setData('text/x-workspace-path', path);
            event.dataTransfer.setData('text/plain', path);
            event.dataTransfer.effectAllowed = 'move';
        }
        setDragMode('move');
        setDragActive(true);
        const target = resolveDropTargetPath();
        setDropTarget(target);
    }, [resolveDropTargetPath]);

    const handleRowDragEnd = useCallback(() => {
        dragDepthRef.current = 0;
        setDragActive(false);
        setDragMode(null);
        setDropTarget(null);
    }, []);

    return html`
        <aside
            class=${`workspace-sidebar${dragActive ? ' workspace-drop-active' : ''}`}
            ref=${sidebarRef}
            onDragEnter=${handleDragEnter}
            onDragOver=${handleDragOver}
            onDragLeave=${handleDragLeave}
            onDrop=${handleDrop}
        >
            <div class="workspace-header">
                <span>Workspace</span>
                <div class="workspace-header-actions">
                    <button class="workspace-create" onClick=${handleCreateFileClick} title="New file" disabled=${uploading}>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                            stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                            <line x1="12" y1="5" x2="12" y2="19" />
                            <line x1="5" y1="12" x2="19" y2="12" />
                        </svg>
                    </button>
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
                ${dragActive && dragMode === 'upload' && html`<div class="workspace-drop-hint">Drop to upload to ${dropTarget || '.'}</div>`}
                ${dragActive && dragMode === 'move' && html`<div class="workspace-drop-hint">Drop to move to ${dropTarget || '.'}</div>`}
                ${uploading && html`<div class="workspace-loading">Uploading…</div>`}
                ${initialLoad && html`<div class="workspace-loading">Loading…</div>`}
                ${error && html`<div class="workspace-error">${error}</div>`}
                ${tree && html`
                    <div class="workspace-tree-list" ref=${treeListRef} tabIndex="0"
                        onClick=${handleTreeClick} onKeyDown=${handleTreeKeyDown}
                        onTouchStart=${handleRowTouchStart} onTouchEnd=${handleRowTouchEnd}
                        onTouchMove=${handleRowTouchMove}>
                        ${rows.map(({ node, depth }) => {
                            const isDir = node.type === 'dir';
                            const isSelected = node.path === selectedPath;
                            const isRenaming = node.path === renamingPath;
                            const isOpen = isDir && expanded.has(node.path);
                            const isDropTarget = dropTarget && node.path === dropTarget;
                            return html`
                                <div
                                    key=${node.path}
                                    class=${`workspace-row${isSelected ? ' selected' : ''}${isDropTarget ? ' drop-target' : ''}`}
                                    style=${{ paddingLeft: `${8 + depth * INDENT}px` }}
                                    data-path=${node.path}
                                    data-type=${node.type}
                                    draggable=${!isRenaming && node.path !== '.'}
                                    onDragStart=${handleRowDragStart}
                                    onDragEnd=${handleRowDragEnd}
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
                                    ${isRenaming
                                        ? html`
                                            <input
                                                class="workspace-rename-input"
                                                ref=${renameInputRef}
                                                value=${renameValue}
                                                onInput=${(e) => setRenameValue(e?.target?.value || '')}
                                                onKeyDown=${(e) => {
                                                    if (e.key === 'Enter') { e.preventDefault(); commitRename(); }
                                                    else if (e.key === 'Escape') { e.preventDefault(); cancelRename(); }
                                                }}
                                                onBlur=${cancelRename}
                                                onClick=${(e) => e.stopPropagation()}
                                            />
                                        `
                                        : html`<span class="workspace-label">${node.name}</span>`}
                                    ${isDir && !isOpen && ((Array.isArray(node.children) && node.children.length > 0) || node.child_count > 0) && html`
                                        <span class="workspace-count">${Array.isArray(node.children) && node.children.length > 0 ? node.children.length : node.child_count}</span>
                                    `}
                                    ${isDir && html`
                                        <button class="workspace-folder-upload" data-upload-target=${node.path}
                                            onClick=${handleFolderUploadClick} title="Upload files to this folder"
                                            disabled=${uploading} aria-hidden="true">
                                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                                                stroke-linecap="round" stroke-linejoin="round">
                                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                                                <polyline points="17 8 12 3 7 8"/>
                                                <line x1="12" y1="3" x2="12" y2="15"/>
                                            </svg>
                                        </button>
                                    `}
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
                        <div class="workspace-preview-actions">
                            <button class="workspace-create" onClick=${handleCreateFileClick} title="New file" disabled=${uploading}>
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                                    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                    <line x1="12" y1="5" x2="12" y2="19" />
                                    <line x1="5" y1="12" x2="19" y2="12" />
                                </svg>
                            </button>
                            ${onOpenEditor && preview?.kind === 'text' && html`
                                <button class="workspace-edit" onClick=${() => onOpenEditor(selectedPath)} title="Edit file">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                                    </svg>
                                </button>
                            `}
                            ${!selectedIsDir && html`
                                <button class="workspace-download workspace-delete" onClick=${handleDeleteFile} title="Delete file">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                                        stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                        <polyline points="3 6 5 6 21 6" />
                                        <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                                        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                                        <line x1="10" y1="11" x2="10" y2="17" />
                                        <line x1="14" y1="11" x2="14" y2="17" />
                                    </svg>
                                </button>
                            `}
                            ${nodeMapRef.current.get(selectedPath)?.type === 'dir'
                                ? html`
                                    <button class="workspace-edit" data-upload-target=${selectedPath}
                                        onClick=${handleFolderUploadClick} title="Upload files to this folder"
                                        disabled=${uploading}>
                                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                                            stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                                            <polyline points="17 8 12 3 7 8"/>
                                            <line x1="12" y1="3" x2="12" y2="15"/>
                                        </svg>
                                    </button>
                                    <a class="workspace-download" href=${getWorkspaceDownloadUrl(selectedPath, showHidden)}
                                    title="Download folder as zip" onClick=${(e) => e.stopPropagation()}>
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                                        stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                                        <polyline points="7 10 12 15 17 10"/>
                                        <line x1="12" y1="15" x2="12" y2="3"/>
                                    </svg>
                                </a>`
                                : html`<button class="workspace-download" onClick=${handleDownload} title="Download">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                                        <polyline points="7 10 12 15 17 10"/>
                                        <line x1="12" y1="15" x2="12" y2="3"/>
                                    </svg>
                                </button>`}
                        </div>
                    </div>
                    ${loadingPreview && html`<div class="workspace-loading">Loading preview…</div>`}
                    ${preview?.error && html`<div class="workspace-error">${preview.error}</div>`}
                    ${nodeMapRef.current.get(selectedPath)?.type === 'dir' && html`
                        <${DiskUsageSunburst} node=${nodeMapRef.current.get(selectedPath)} showHidden=${showHidden} />
                    `}
                    ${preview && !preview.error && nodeMapRef.current.get(selectedPath)?.type !== 'dir' && html`
                        <div class="workspace-preview-meta">
                            ${preview.size ? html`<span>${formatFileSize(preview.size)}</span>` : ''}
                            ${preview.mtime ? html`<span>${formatTimestamp(preview.mtime)}</span>` : ''}
                            ${preview.truncated ? html`<span>truncated</span>` : ''}
                        </div>
                        ${preview.kind === 'image' && html`
                            <div class="workspace-preview-image">
                                <img src=${`${preview.url || getWorkspaceRawUrl(preview.path)}${preview.mtime ? '&t=' + encodeURIComponent(preview.mtime) : ''}`} alt="preview" />
                            </div>
                        `}
                        ${preview.kind === 'text' && html`
                            ${preview.content_type === 'text/markdown'
                                ? html`<div class="workspace-preview-text" dangerouslySetInnerHTML=${{ __html: rewriteRelativeUrls(renderPreviewMarkdown(preview.text || ''), preview.path) }} />`
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
            <input type="file" multiple ref=${folderUploadRef} onChange=${handleFolderUploadChange}
                style="display:none" />
        </aside>
    `;
}
