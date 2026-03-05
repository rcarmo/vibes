import { html, useCallback, useEffect, useMemo, useRef, useState } from '../vendor/preact-htm.js';
import {
    EditorState,
    EditorView,
    minimalSetup,
    lineNumbers,
    highlightActiveLine,
    highlightSpecialChars,
    javascript,
    python,
    markdown,
    go,
    json,
    css,
    html as htmlLang,
    yaml,
    sql,
    xml,
    StreamLanguage,
    HighlightStyle,
    classHighlighter,
    syntaxHighlighting,
    tags,
    shell,
    keymap,
    indentWithTab,
    search,
    searchKeymap,
} from '../vendor/codemirror.js';

const MONO_STACK = 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace';
const shellLanguage = StreamLanguage.define(shell);

const headingStyle = HighlightStyle.define([
    { tag: tags.heading1, fontWeight: 'bold', fontSize: '1.3em', textDecoration: 'none' },
    { tag: tags.heading2, fontWeight: 'bold', fontSize: '1.2em', textDecoration: 'none' },
    { tag: tags.heading3, fontWeight: 'bold', fontSize: '1.1em', textDecoration: 'none' },
    { tag: tags.heading4, fontWeight: 'bold', textDecoration: 'none' },
    { tag: tags.heading5, fontWeight: 'bold', textDecoration: 'none' },
    { tag: tags.heading6, fontWeight: 'bold', textDecoration: 'none' },
]);

const languageForPath = (path) => {
    const lower = String(path || '').toLowerCase();
    if (lower.endsWith('.py')) return python();
    if (lower.endsWith('.ts') || lower.endsWith('.tsx')) return javascript({ typescript: true, jsx: lower.endsWith('.tsx') });
    if (lower.endsWith('.js') || lower.endsWith('.jsx')) return javascript({ jsx: lower.endsWith('.jsx') });
    if (lower.endsWith('.md') || lower.endsWith('.markdown')) return markdown();
    if (lower.endsWith('.go')) return go();
    if (lower.endsWith('.json') || lower.endsWith('.jsonl')) return json();
    if (lower.endsWith('.css') || lower.endsWith('.scss')) return css();
    if (lower.endsWith('.html') || lower.endsWith('.htm')) return htmlLang();
    if (lower.endsWith('.yaml') || lower.endsWith('.yml')) return yaml();
    if (lower.endsWith('.sql') || lower.endsWith('.sqlite')) return sql();
    if (lower.endsWith('.xml') || lower.endsWith('.svg') || lower.endsWith('.plist')) return xml();
    if (lower.endsWith('.sh') || lower.endsWith('.bash') || lower.endsWith('.zsh')) return shellLanguage;
    return null;
};

/**
 * Lightweight CodeMirror editor wrapper.
 */
export function WorkspaceEditor({
    path,
    content,
    loading,
    error,
    saving,
    saveError,
    savedAt,
    onSave,
    onClose,
}) {
    const hostRef = useRef(null);
    const viewRef = useRef(null);
    const initialContentRef = useRef(content || '');
    const [dirty, setDirty] = useState(false);

    const languageExtension = useMemo(() => languageForPath(path), [path]);

    const updateDirty = useCallback(() => {
        const view = viewRef.current;
        if (!view) return;
        const current = view.state.doc.toString();
        setDirty(current !== initialContentRef.current);
    }, []);

    const resetContent = useCallback((nextContent) => {
        const view = viewRef.current;
        if (!view) return;
        const current = view.state.doc.toString();
        if (current === nextContent) {
            initialContentRef.current = nextContent;
            setDirty(false);
            return;
        }
        view.dispatch({
            changes: { from: 0, to: view.state.doc.length, insert: nextContent },
        });
        initialContentRef.current = nextContent;
        setDirty(false);
    }, []);

    const handleSave = useCallback(() => {
        if (saving || loading) return;
        const view = viewRef.current;
        if (!view) return;
        const value = view.state.doc.toString();
        onSave?.(value);
    }, [saving, loading, onSave]);

    useEffect(() => {
        const host = hostRef.current;
        if (!host) return;

        const extensions = [
            minimalSetup,
            lineNumbers(),
            highlightActiveLine(),
            highlightSpecialChars(),
            EditorView.lineWrapping,
            syntaxHighlighting(headingStyle),
            syntaxHighlighting(classHighlighter),
            search(),
            keymap.of([...searchKeymap, indentWithTab, { key: 'Mod-s', run: () => { handleSave(); return true; } }]),
            EditorView.updateListener.of((update) => {
                if (update.docChanged) updateDirty();
            }),
            EditorView.theme({
                '&': { height: '100%', fontFamily: MONO_STACK },
                '.cm-scroller': { fontFamily: MONO_STACK },
                '.cm-content': { fontFamily: MONO_STACK, fontSize: '12px' },
                '.cm-gutters': { fontFamily: MONO_STACK },
            }),
        ];

        if (languageExtension) extensions.push(languageExtension);

        const state = EditorState.create({
            doc: content || '',
            extensions,
        });

        const view = new EditorView({ state, parent: host });
        viewRef.current = view;
        initialContentRef.current = content || '';
        setDirty(false);

        return () => {
            view.destroy();
            viewRef.current = null;
        };
    }, [path, languageExtension]);

    useEffect(() => {
        if (content === undefined) return;
        resetContent(content || '');
    }, [content, resetContent]);

    useEffect(() => {
        if (!savedAt) return;
        const view = viewRef.current;
        if (!view) return;
        initialContentRef.current = view.state.doc.toString();
        setDirty(false);
    }, [savedAt]);

    // Escape to close when clean. Cmd/Ctrl+S to save (intercepts browser dialog).
    useEffect(() => {
        const onKeyDown = (e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 's') {
                e.preventDefault();
                handleSave();
                return;
            }
            if (e.key === 'Escape' && !e.defaultPrevented && !dirty) {
                onClose?.();
            }
        };
        document.addEventListener('keydown', onKeyDown);
        return () => document.removeEventListener('keydown', onKeyDown);
    }, [dirty, onClose, handleSave]);

    // Drag-to-resize: right edge handle (mouse + touch)
    const resizeRef = useRef(null);
    useEffect(() => {
        const handle = resizeRef.current;
        if (!handle) return;
        let startX = 0;
        let startW = 0;
        const clamp = (v) => Math.max(280, Math.min(window.innerWidth * 0.7, v));
        const applyWidth = (clientX) => {
            const newW = clamp(startW + (clientX - startX));
            handle.parentElement.style.width = newW + 'px';
            handle.parentElement.style.minWidth = newW + 'px';
        };
        const onMouseMove = (e) => applyWidth(e.clientX);
        const onMouseUp = () => {
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        };
        const onMouseDown = (e) => {
            e.preventDefault();
            startX = e.clientX;
            startW = handle.parentElement.getBoundingClientRect().width;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        };
        const onTouchMove = (e) => {
            if (e.touches.length === 1) applyWidth(e.touches[0].clientX);
        };
        const onTouchEnd = () => {
            document.removeEventListener('touchmove', onTouchMove);
            document.removeEventListener('touchend', onTouchEnd);
        };
        const onTouchStart = (e) => {
            if (e.touches.length !== 1) return;
            startX = e.touches[0].clientX;
            startW = handle.parentElement.getBoundingClientRect().width;
            document.addEventListener('touchmove', onTouchMove, { passive: true });
            document.addEventListener('touchend', onTouchEnd);
        };
        handle.addEventListener('mousedown', onMouseDown);
        handle.addEventListener('touchstart', onTouchStart, { passive: true });
        return () => {
            handle.removeEventListener('mousedown', onMouseDown);
            handle.removeEventListener('touchstart', onTouchStart);
        };
    }, []);

    return html`
        <div class="editor-pane">
            <div class="editor-resize-handle" ref=${resizeRef}></div>
            <div class="editor-header">
                <div class="editor-title" title=${path || ''}>${path || 'Untitled file'}</div>
                <div class="editor-actions">
                    <button class="editor-button" onClick=${onClose} title="Close editor">Close</button>
                    <button
                        class="editor-button primary"
                        onClick=${handleSave}
                        disabled=${!dirty || saving || loading}
                        title=${dirty ? 'Save changes' : 'No changes to save'}
                    >
                        ${saving ? 'Saving…' : 'Save'}
                    </button>
                </div>
            </div>
            ${loading && html`<div class="editor-status">Loading…</div>`}
            ${error && html`<div class="editor-error">${error}</div>`}
            <div class="editor-body${loading || error ? ' disabled' : ''}">
                <div class="editor-codemirror" ref=${hostRef}></div>
            </div>
            ${saveError && html`<div class="editor-error">${saveError}</div>`}
            ${!saveError && !error && html`
                <div class="editor-status">
                    ${dirty ? 'Unsaved changes' : savedAt ? 'All changes saved' : 'Ready'}
                </div>
            `}
        </div>
    `;
}
