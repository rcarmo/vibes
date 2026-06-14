import { describe, expect, test } from 'bun:test';
import {
  flattenTree,
  formatWorkspaceFileSize,
  formatWorkspaceTimestamp,
  isHiddenNode,
  mergeTree,
  replaceNodeAtPath,
  rewriteRelativeUrls,
  treeSignature,
} from '../../static/js/features/workspace/explorer-utils.ts';
import type { WorkspaceTreeNode } from '../../static/js/features/workspace/sunburst-utils.ts';

const tree: WorkspaceTreeNode = {
  name: '.', path: '.', type: 'dir', children: [
    { name: 'a.md', path: 'a.md', type: 'file', size: 10 },
    { name: '.env', path: '.env', type: 'file', size: 20 },
    { name: 'src', path: 'src', type: 'dir', children: [
      { name: 'main.ts', path: 'src/main.ts', type: 'file', size: 30 },
    ] },
  ],
};

describe('workspace explorer utilities', () => {
  test('rewrites relative image/source URLs', () => {
    const out = rewriteRelativeUrls('<img src="pic.png"><source src="./clip.webm"><img src="/abs.png"><img src="https://x/y.png">', 'docs/readme.md', (path) => `/raw?path=${encodeURIComponent(path)}`);
    expect(out).toContain('src="/raw?path=docs%2Fpic.png"');
    expect(out).toContain('src="/raw?path=docs%2Fclip.webm"');
    expect(out).toContain('src="/abs.png"');
    expect(out).toContain('src="https://x/y.png"');
  });

  test('formats metadata', () => {
    expect(formatWorkspaceFileSize(512)).toBe('512 B');
    expect(formatWorkspaceFileSize(2048)).toBe('2.0 KB');
    expect(formatWorkspaceFileSize(Number.NaN)).toBe('');
    expect(formatWorkspaceTimestamp('not-a-date')).toBe('not-a-date');
  });

  test('flattens visible tree and creates signatures', () => {
    const expanded = new Set(['.', 'src']);
    expect(isHiddenNode(tree.children?.[1])).toBe(true);
    expect(flattenTree(tree, expanded, false).map((row) => row.node.path)).toEqual(['.', 'a.md', 'src', 'src/main.ts']);
    expect(flattenTree(tree, expanded, true).map((row) => row.node.path)).toEqual(['.', 'a.md', '.env', 'src', 'src/main.ts']);
    expect(treeSignature(tree, expanded, false)).toBe('.|dir|a.md|file|src|dir|src/main.ts|file');
  });

  test('merges and replaces tree nodes', () => {
    const previous: WorkspaceTreeNode = { name: '.', path: '.', type: 'dir', children: [{ name: 'src', path: 'src', type: 'dir', children: [{ name: 'old.ts', path: 'src/old.ts', type: 'file' }] }] };
    const shallowNext: WorkspaceTreeNode = { name: '.', path: '.', type: 'dir' };
    expect(mergeTree(previous, shallowNext)).toBe(previous);

    const replacement: WorkspaceTreeNode = { name: 'src', path: 'src', type: 'dir', children: [{ name: 'new.ts', path: 'src/new.ts', type: 'file' }] };
    const replaced = replaceNodeAtPath(previous, 'src', replacement);
    expect(replaced?.children?.[0].children?.[0].path).toBe('src/new.ts');
  });
});
