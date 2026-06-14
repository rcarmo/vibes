export const SUNBURST_PALETTE = [
    '#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f',
    '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac',
];

export const SUNBURST_MAX_DEPTH = 4;
export const SUNBURST_TAU = 2 * Math.PI;

export interface WorkspaceTreeNode {
    name?: string;
    path?: string;
    type?: string;
    size?: number;
    children?: WorkspaceTreeNode[];
    child_count?: number;
}

export interface SunburstArc {
    node: WorkspaceTreeNode;
    size: number;
    depth: number;
    startAngle: number;
    endAngle: number;
    color: string;
}

export function formatSize(bytes: number | null | undefined): string {
    if (bytes == null || bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    const val = bytes / Math.pow(1024, i);
    return `${val < 10 ? val.toFixed(1) : Math.round(val)} ${units[i]}`;
}

export function computeSize(node: WorkspaceTreeNode | null | undefined): number {
    if (!node) return 0;
    if (node.type !== 'dir') return node.size || 0;
    const children = node.children;
    if (!children || children.length === 0) return 0;
    let total = 0;
    for (const child of children) {
        total += computeSize(child);
    }
    return total;
}

function buildArcs(
    node: WorkspaceTreeNode,
    startAngle: number,
    endAngle: number,
    depth: number,
    parentIndex: number,
    result: SunburstArc[],
    maxDepth: number,
): void {
    if (depth >= maxDepth) return;
    const children = node.children;
    if (!children || children.length === 0) return;

    const resolved: Array<{ node: WorkspaceTreeNode; size: number }> = [];
    for (const child of children) {
        if (!child) continue;
        const size = computeSize(child);
        if (size > 0) resolved.push({ node: child, size });
    }
    if (resolved.length === 0) return;

    const totalSize = resolved.reduce((acc, item) => acc + item.size, 0);
    if (totalSize === 0) return;
    const span = endAngle - startAngle;
    let angle = startAngle;

    for (let i = 0; i < resolved.length; i += 1) {
        const { node: child, size } = resolved[i];
        const sweep = (size / totalSize) * span;
        if (sweep < 0.005) {
            angle += sweep;
            continue;
        }
        const colorIdx = depth === 0 ? i % SUNBURST_PALETTE.length : parentIndex;
        result.push({
            node: child,
            size,
            depth,
            startAngle: angle,
            endAngle: angle + sweep,
            color: SUNBURST_PALETTE[colorIdx],
        });
        if (child.type === 'dir') {
            buildArcs(child, angle, angle + sweep, depth + 1, colorIdx, result, maxDepth);
        }
        angle += sweep;
    }
}

export function buildSunburstArcs(
    node: WorkspaceTreeNode | null | undefined,
    startAngle = -Math.PI / 2,
    endAngle = -Math.PI / 2 + SUNBURST_TAU,
    maxDepth = SUNBURST_MAX_DEPTH,
): SunburstArc[] {
    if (!node || computeSize(node) === 0) return [];
    const result: SunburstArc[] = [];
    buildArcs(node, startAngle, endAngle, 0, 0, result, maxDepth);
    return result;
}

export function arcPath(cx: number, cy: number, r1: number, r2: number, a0: number, a1: number): string {
    const cos0 = Math.cos(a0);
    const sin0 = Math.sin(a0);
    const cos1 = Math.cos(a1);
    const sin1 = Math.sin(a1);
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const ox1 = cx + r1 * cos0;
    const oy1 = cy + r1 * sin0;
    const ox2 = cx + r2 * cos0;
    const oy2 = cy + r2 * sin0;
    const ix1 = cx + r1 * cos1;
    const iy1 = cy + r1 * sin1;
    const ix2 = cx + r2 * cos1;
    const iy2 = cy + r2 * sin1;
    return [
        `M ${ox2} ${oy2}`,
        `A ${r2} ${r2} 0 ${large} 1 ${ix2} ${iy2}`,
        `L ${ix1} ${iy1}`,
        `A ${r1} ${r1} 0 ${large} 0 ${ox1} ${oy1}`,
        'Z',
    ].join(' ');
}

export function findNode(root: WorkspaceTreeNode | null | undefined, targetPath: string | null | undefined): WorkspaceTreeNode | null {
    if (!root) return null;
    if (root.path === targetPath) return root;
    if (!Array.isArray(root.children)) return null;
    for (const child of root.children) {
        const found = findNode(child, targetPath);
        if (found) return found;
    }
    return null;
}
