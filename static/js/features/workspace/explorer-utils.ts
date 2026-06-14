import type { WorkspaceTreeNode } from './sunburst-utils.ts';

export interface FlattenedWorkspaceRow {
    node: WorkspaceTreeNode;
    depth: number;
}

export type RawUrlBuilder = (path: string) => string;

/**
 * Rewrite relative src attributes in rendered HTML so images and sources inside
 * markdown previews resolve against the workspace raw endpoint.
 */
export function rewriteRelativeUrls(htmlStr: string, filePath: string | null | undefined, getRawUrl: RawUrlBuilder): string {
    if (!filePath) return htmlStr;
    const dir = filePath.includes('/') ? filePath.slice(0, filePath.lastIndexOf('/')) : '.';
    return htmlStr.replace(
        /(<(?:img|source)\s[^>]*?\bsrc\s*=\s*["'])([^"']+)(["'])/gi,
        (match, pre, url, post) => {
            if (/^(?:https?:|data:|\/)/i.test(url)) return match;
            const clean = url.replace(/^\.\//, '');
            const resolved = dir === '.' ? clean : `${dir}/${clean}`;
            return `${pre}${getRawUrl(resolved)}${post}`;
        },
    );
}

export function formatWorkspaceFileSize(bytes: unknown): string {
    if (!Number.isFinite(bytes)) return '';
    const value = Number(bytes);
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatWorkspaceTimestamp(value: string | number | Date | null | undefined): string | number | Date {
    const date = new Date(value ?? '');
    if (Number.isNaN(date.getTime())) return value || '';
    return date.toLocaleString();
}

export function isHiddenNode(node: WorkspaceTreeNode | null | undefined): boolean {
    if (!node || !node.name) return false;
    if (node.path === '.') return false;
    return node.name.startsWith('.');
}

export function flattenTree(
    node: WorkspaceTreeNode | null | undefined,
    expanded: Set<string>,
    showHidden: boolean,
    depth = 0,
    rows: FlattenedWorkspaceRow[] = [],
): FlattenedWorkspaceRow[] {
    if (!node) return rows;
    if (!showHidden && isHiddenNode(node)) return rows;
    rows.push({ node, depth });
    if (node.type === 'dir' && Array.isArray(node.children) && expanded.has(node.path || '')) {
        for (const child of node.children) flattenTree(child, expanded, showHidden, depth + 1, rows);
    }
    return rows;
}

/**
 * Signature of visible structure only: path + type for expanded nodes.
 */
export function treeSignature(node: WorkspaceTreeNode | null | undefined, expanded: Set<string>, showHidden: boolean): string {
    if (!node) return '';
    const parts: Array<string | undefined> = [];
    const walk = (item: WorkspaceTreeNode | null | undefined) => {
        if (!item) return;
        if (!showHidden && isHiddenNode(item)) return;
        parts.push(item.path, item.type);
        if (item.children && expanded?.has(item.path || '')) {
            for (const child of item.children) walk(child);
        }
    };
    walk(node);
    return parts.join('|');
}

export function mergeTree(prev: WorkspaceTreeNode | null | undefined, next: WorkspaceTreeNode | null | undefined): WorkspaceTreeNode | null {
    if (!next) return null;
    if (!prev) return next;
    if (prev.path !== next.path || prev.type !== next.type) return next;

    const prevKids = Array.isArray(prev.children) ? prev.children : null;
    const nextKids = Array.isArray(next.children) ? next.children : null;

    // Server hit depth limit and returned no children – keep what we had.
    if (!nextKids) return prev;

    const prevMap = prevKids ? new Map(prevKids.map((child) => [child?.path, child])) : new Map<string | undefined, WorkspaceTreeNode>();
    let changed = !prevKids || prevKids.length !== nextKids.length;
    const merged = nextKids.map((child) => {
        const previousChild = prevMap.get(child.path);
        const mergedChild = mergeTree(previousChild, child);
        if (mergedChild !== previousChild) changed = true;
        return mergedChild || child;
    });
    return changed ? { ...next, children: merged } : prev;
}

export function replaceNodeAtPath(node: WorkspaceTreeNode | null | undefined, targetPath: string, nextNode: WorkspaceTreeNode): WorkspaceTreeNode | null | undefined {
    if (!node) return node;
    if (node.path === targetPath) return mergeTree(node, nextNode);
    if (!Array.isArray(node.children)) return node;
    let changed = false;
    const children = node.children.map((child) => {
        const updated = replaceNodeAtPath(child, targetPath, nextNode);
        if (updated !== child) changed = true;
        return updated || child;
    });
    return changed ? { ...node, children } : node;
}
