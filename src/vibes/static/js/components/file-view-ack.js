// Browser acknowledgement requires the exact loaded editor, never a basename match.
export async function waitForFileView(path, isCurrent, { pane = () => document.querySelector('.editor-pane'), pause = () => new Promise(resolve => setTimeout(resolve, 25)), attempts = 80 } = {}) {
    for (let i = 0; i < attempts; i++) {
        if (!isCurrent()) return 'rejected';
        const editor = pane();
        if (editor?.dataset.editorPath === path && editor.dataset.editorLoading === 'false') {
            return editor.dataset.editorError === 'false' && editor.querySelector('.cm-content') ? 'opened' : 'rejected';
        }
        await pause();
    }
    return 'rejected';
}
