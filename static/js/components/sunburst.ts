import { html, useState, useEffect, useCallback, useMemo, useRef } from '../vendor/preact-htm.js';
import { getWorkspaceTree } from '../api.ts';
import {
    arcPath,
    buildSunburstArcs,
    computeSize,
    findNode,
    formatSize,
    type SunburstArc,
    type WorkspaceTreeNode,
} from '../features/workspace/sunburst-utils.ts';

const FETCH_DEPTH = 8;
const CX = 100;
const CY = 100;
const INNER_R = 20;
const RING_W = 18;

interface WorkspaceTreePayload {
    root?: WorkspaceTreeNode;
}

interface DiskUsageSunburstProps {
    node?: WorkspaceTreeNode | null;
    showHidden?: boolean;
}

// Simple LRU cache for deep tree fetches.
const treeCache = new Map<string, WorkspaceTreeNode>();
const CACHE_MAX = 16;
function cacheGet(key: string): WorkspaceTreeNode | null { return treeCache.get(key) || null; }
function cacheSet(key: string, value: WorkspaceTreeNode): void {
    treeCache.delete(key); // move to end
    treeCache.set(key, value);
    if (treeCache.size > CACHE_MAX) {
        const first = treeCache.keys().next().value;
        if (first) treeCache.delete(first);
    }
}

export function DiskUsageSunburst({ node, showHidden = false }: DiskUsageSunburstProps) {
    const [deepTree, setDeepTree] = useState(null as WorkspaceTreeNode | null);
    const [loading, setLoading] = useState(false);
    const [drillPath, setDrillPath] = useState(null as string | null);
    const [hovered, setHovered] = useState(null as number | null);
    const folderPath = node?.path;
    const fetchIdRef = useRef(0);

    // Fetch a deep tree for the selected folder (with cache).
    useEffect(() => {
        if (!folderPath) return;
        const id = ++fetchIdRef.current;
        setDrillPath(null);
        setHovered(null);

        const cacheKey = `${folderPath}|${showHidden}`;
        const cached = cacheGet(cacheKey);
        if (cached) {
            setDeepTree(cached);
            setLoading(false);
            return;
        }

        setLoading(true);
        getWorkspaceTree(folderPath, FETCH_DEPTH, showHidden)
            .then((data) => {
                if (id !== fetchIdRef.current) return;
                const payload = data as WorkspaceTreePayload;
                if (payload?.root) {
                    cacheSet(cacheKey, payload.root);
                    setDeepTree(payload.root);
                }
            })
            .catch(() => {})
            .finally(() => { if (id === fetchIdRef.current) setLoading(false); });
    }, [folderPath, showHidden]);

    // Invalidate cache on workspace updates.
    useEffect(() => {
        const handler = () => { treeCache.clear(); };
        window.addEventListener('workspace-update', handler);
        return () => window.removeEventListener('workspace-update', handler);
    }, []);

    const root = useMemo(() => {
        if (!deepTree) return null;
        if (!drillPath) return deepTree;
        return findNode(deepTree, drillPath) || deepTree;
    }, [deepTree, drillPath]);

    const totalSize = useMemo(() => computeSize(root), [root]);

    const arcs = useMemo(() => buildSunburstArcs(root), [root]) as SunburstArc[];

    const handleArcClick = useCallback((arc: SunburstArc) => {
        if (arc.node.type === 'dir' && arc.node.children && arc.node.children.length > 0) {
            setDrillPath(arc.node.path || null);
            setHovered(null);
        }
    }, []);

    const handleCenterClick = useCallback(() => {
        if (!drillPath) return;
        // Navigate up: find parent path, or null to return to deepTree root.
        const parent = drillPath.includes('/')
            ? drillPath.substring(0, drillPath.lastIndexOf('/'))
            : null;
        setDrillPath(parent || null);
        setHovered(null);
    }, [drillPath]);

    const legendEntries = useMemo(() => {
        const seen = new Set<string>();
        return arcs.filter((arc) => {
            const path = arc.node.path || '';
            if (arc.depth !== 0 || seen.has(path)) return false;
            seen.add(path);
            return true;
        });
    }, [arcs]) as SunburstArc[];

    if (!node) return null;
    if (loading) return html`<div style="text-align:center;color:var(--text-secondary,#888);font-size:13px;padding:16px 0;">Loading disk usage…</div>`;
    if (!deepTree || !root) return null;

    const centerLabel = root.name === '.' ? 'root' : (root.name || 'root');
    const canGoUp = Boolean(drillPath);

    return html`
        <div style="position:relative;width:100%;max-width:300px;margin:0 auto;">
            <svg viewBox="0 0 200 200" style="width:100%;height:auto;">
                ${arcs.map((arc, i) => {
                    const r1 = INNER_R + arc.depth * RING_W;
                    const r2 = r1 + RING_W - 1;
                    const d = arcPath(CX, CY, r1, r2, arc.startAngle, arc.endAngle);
                    const isHovered = hovered === i;
                    return html`
                        <path
                            key=${i}
                            d=${d}
                            fill=${arc.color}
                            opacity=${hovered != null && !isHovered ? 0.4 : 0.85}
                            stroke="var(--bg-primary, #fff)"
                            stroke-width="0.5"
                            style="cursor:pointer;transition:opacity 0.15s"
                            onMouseEnter=${() => setHovered(i)}
                            onMouseLeave=${() => setHovered(null)}
                            onClick=${() => handleArcClick(arc)}
                        />
                    `;
                })}
                <circle
                    cx=${CX} cy=${CY} r=${INNER_R}
                    fill="var(--bg-primary, #1a1a2e)"
                    stroke="var(--border-color, #333)"
                    stroke-width="0.5"
                    style="cursor:${canGoUp ? 'pointer' : 'default'}"
                    onClick=${handleCenterClick}
                />
                <text
                    x=${CX} y=${CY - 5}
                    text-anchor="middle"
                    fill="var(--text-primary, #ccc)"
                    font-size="7"
                    font-weight="bold"
                    style="pointer-events:none"
                >${centerLabel.toUpperCase()}</text>
                <text
                    x=${CX} y=${CY + 6}
                    text-anchor="middle"
                    fill="var(--text-secondary, #888)"
                    font-size="6"
                    style="pointer-events:none"
                >${formatSize(totalSize)}</text>
                ${canGoUp && html`
                    <text
                        x=${CX} y=${CY + 14}
                        text-anchor="middle"
                        fill="var(--accent-color, #4e79a7)"
                        font-size="4"
                        style="pointer-events:none"
                    >▲ UP</text>
                `}
            </svg>
            ${hovered != null && arcs[hovered] && html`
                <div style="
                    position:absolute;top:4px;left:50%;transform:translateX(-50%);
                    background:var(--bg-primary,#1a1a2e);
                    border:1px solid var(--border-color,#333);
                    color:var(--text-primary,#ccc);
                    padding:3px 8px;border-radius:4px;font-size:12px;
                    pointer-events:none;white-space:nowrap;z-index:10;
                ">
                    <strong>${arcs[hovered].node.name}</strong> — ${formatSize(arcs[hovered].size)}
                </div>
            `}
            ${totalSize === 0 && html`
                <div style="
                    text-align:center;color:var(--text-secondary,#888);
                    font-size:13px;padding:8px 0;
                ">No size data available</div>
            `}
            ${legendEntries.length > 0 && html`
                <div style="
                    display:flex;flex-wrap:wrap;gap:2px 10px;
                    padding:4px 0 0;font-size:11px;
                    color:var(--text-secondary,#888);
                    justify-content:center;
                ">
                    ${legendEntries.map((entry) => html`
                        <span
                            key=${entry.node.path}
                            style="display:inline-flex;align-items:center;gap:3px;cursor:pointer;"
                            onClick=${() => handleArcClick(entry)}
                            title=${`${entry.node.name} — ${formatSize(entry.size)}`}
                        >
                            <span style="
                                display:inline-block;width:8px;height:8px;
                                border-radius:2px;background:${entry.color};
                                flex-shrink:0;
                            "></span>
                            <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:90px;">
                                ${entry.node.name}
                            </span>
                            <span style="opacity:0.7;">${formatSize(entry.size)}</span>
                        </span>
                    `)}
                </div>
            `}
        </div>
    `;
}
