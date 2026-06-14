import { describe, expect, test } from 'bun:test';
import { arcPath, buildSunburstArcs, computeSize, findNode, formatSize, type WorkspaceTreeNode } from '../../static/js/features/workspace/sunburst-utils.ts';

const tree: WorkspaceTreeNode = {
  name: 'root',
  path: '.',
  type: 'dir',
  children: [
    { name: 'a.txt', path: 'a.txt', type: 'file', size: 1024 },
    { name: 'folder', path: 'folder', type: 'dir', children: [
      { name: 'b.bin', path: 'folder/b.bin', type: 'file', size: 2048 },
    ] },
  ],
};

describe('sunburst utilities', () => {
  test('formats and computes sizes', () => {
    expect(formatSize(0)).toBe('0 B');
    expect(formatSize(1024)).toBe('1.0 KB');
    expect(formatSize(1536)).toBe('1.5 KB');
    expect(computeSize(tree)).toBe(3072);
  });

  test('builds arcs and finds nodes', () => {
    const arcs = buildSunburstArcs(tree);
    expect(arcs.length).toBeGreaterThanOrEqual(3);
    expect(arcs[0].node.path).toBe('a.txt');
    expect(findNode(tree, 'folder/b.bin')?.name).toBe('b.bin');
    expect(findNode(tree, 'missing')).toBeNull();
  });

  test('creates SVG arc paths', () => {
    const d = arcPath(100, 100, 20, 40, 0, Math.PI / 2);
    expect(d).toStartWith('M 140 100');
    expect(d).toEndWith('Z');
  });
});
