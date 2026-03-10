import { html, useState, useCallback, useMemo } from '../vendor/preact-htm.js';

const PALETTE = [
    '#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f',
    '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac',
];

const MAX_DEPTH = 4;
const CX = 100;
const CY = 100;
const INNER_R = 20;
const RING_W = 18;
const TAU = 2 * Math.PI;

function formatSize(bytes) {
    if (bytes == null || bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    const val = bytes / Math.pow(1024, i);
    return `${val < 10 ? val.toFixed(1) : Math.round(val)} ${units[i]}`;
}

function computeSize(node, nodeMap) {
    if (!node) return 0;
    if (node.type !== 'dir') return node.size || 0;
    const children = node.children;
    if (!children || children.length === 0) return 0;
    let total = 0;
    for (const child of children) {
        const resolved = typeof child === 'string' ? nodeMap.get(child) : child;
        if (!resolved) continue;
        total += computeSize(resolved, nodeMap);
    }
    return total;
}

function buildArcs(node, nodeMap, startAngle, endAngle, depth, parentIndex, result) {
    if (depth >= MAX_DEPTH) return;
    const children = node.children;
    if (!children || children.length === 0) return;

    const resolved = [];
    for (const child of children) {
        const c = typeof child === 'string' ? nodeMap.get(child) : child;
        if (!c) continue;
        const s = computeSize(c, nodeMap);
        if (s > 0) resolved.push({ node: c, size: s });
    }
    if (resolved.length === 0) return;

    const totalSize = resolved.reduce((a, b) => a + b.size, 0);
    if (totalSize === 0) return;
    const span = endAngle - startAngle;
    let angle = startAngle;

    for (let i = 0; i < resolved.length; i++) {
        const { node: child, size } = resolved[i];
        const sweep = (size / totalSize) * span;
        if (sweep < 0.005) { angle += sweep; continue; }
        const colorIdx = depth === 0 ? i % PALETTE.length : parentIndex;
        result.push({
            node: child,
            size,
            depth,
            startAngle: angle,
            endAngle: angle + sweep,
            color: PALETTE[colorIdx],
        });
        if (child.type === 'dir') {
            buildArcs(child, nodeMap, angle, angle + sweep, depth + 1, colorIdx, result);
        }
        angle += sweep;
    }
}

function arcPath(cx, cy, r1, r2, a0, a1) {
    const cos0 = Math.cos(a0), sin0 = Math.sin(a0);
    const cos1 = Math.cos(a1), sin1 = Math.sin(a1);
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const ox1 = cx + r1 * cos0, oy1 = cy + r1 * sin0;
    const ox2 = cx + r2 * cos0, oy2 = cy + r2 * sin0;
    const ix1 = cx + r1 * cos1, iy1 = cy + r1 * sin1;
    const ix2 = cx + r2 * cos1, iy2 = cy + r2 * sin1;
    return [
        `M ${ox2} ${oy2}`,
        `A ${r2} ${r2} 0 ${large} 1 ${ix2} ${iy2}`,
        `L ${ix1} ${iy1}`,
        `A ${r1} ${r1} 0 ${large} 0 ${ox1} ${oy1}`,
        'Z',
    ].join(' ');
}

export function DiskUsageSunburst({ node, nodeMap }) {
    const [drillPath, setDrillPath] = useState(null);
    const [hovered, setHovered] = useState(null);

    const root = useMemo(() => {
        if (!drillPath) return node;
        return nodeMap.get(drillPath) || node;
    }, [node, nodeMap, drillPath]);

    const totalSize = useMemo(() => computeSize(root, nodeMap), [root, nodeMap]);

    const arcs = useMemo(() => {
        if (!root || totalSize === 0) return [];
        const result = [];
        buildArcs(root, nodeMap, -Math.PI / 2, -Math.PI / 2 + TAU, 0, 0, result);
        return result;
    }, [root, nodeMap, totalSize]);

    const handleArcClick = useCallback((arc) => {
        if (arc.node.type === 'dir' && arc.node.children && arc.node.children.length > 0) {
            setDrillPath(arc.node.path);
            setHovered(null);
        }
    }, []);

    const handleCenterClick = useCallback(() => {
        if (!drillPath) return;
        const parent = drillPath.includes('/') ? drillPath.substring(0, drillPath.lastIndexOf('/')) : null;
        setDrillPath(parent === '' ? null : parent);
        setHovered(null);
    }, [drillPath]);

    if (!node) return null;

    const centerLabel = root.name === '.' ? 'root' : root.name;

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
                    style="cursor:${drillPath ? 'pointer' : 'default'}"
                    onClick=${handleCenterClick}
                />
                <text
                    x=${CX} y=${CY - 4}
                    text-anchor="middle"
                    fill="var(--text-primary, #ccc)"
                    font-size="5"
                    font-weight="bold"
                >${centerLabel}</text>
                <text
                    x=${CX} y=${CY + 6}
                    text-anchor="middle"
                    fill="var(--text-secondary, #888)"
                    font-size="4.5"
                >${formatSize(totalSize)}</text>
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
        </div>
    `;
}
