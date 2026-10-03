import { test, expect } from 'bun:test';
import { waitForFileView } from '../../src/vibes/static/js/components/file-view-ack.js';
const pane = (path, loading = false, error = false) => ({ dataset: { editorPath: path, editorLoading: String(loading), editorError: String(error) }, querySelector: () => ({}) });
test('ack requires exact path and completed loading', async () => {
    let current = pane('other/note.txt');
    expect(await waitForFileView('wanted/note.txt', () => true, { pane: () => current, pause: async () => {}, attempts: 1 })).toBe('rejected');
    current = pane('wanted/note.txt', true);
    expect(await waitForFileView('wanted/note.txt', () => true, { pane: () => current, pause: async () => { current = pane('wanted/note.txt'); }, attempts: 2 })).toBe('opened');
});
test('changed chat and failed editor never acknowledge success', async () => {
    expect(await waitForFileView('note.txt', () => false, { pane: () => pane('note.txt') })).toBe('rejected');
    expect(await waitForFileView('note.txt', () => true, { pane: () => pane('note.txt', false, true) })).toBe('rejected');
});
