import { html, useCallback, useEffect, useMemo, useRef, useState } from '../vendor/preact-htm.js';
import {
    EditorState,
    EditorView,
    Compartment,
    minimalSetup,
    lineNumbers,
    highlightActiveLine,
    highlightActiveLineGutter,
    highlightSpecialChars,
    scrollPastEnd,
    showPanel,
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
    syntaxHighlighting,
    indentOnInput,
    indentUnit,
    tags,
    classHighlighter,
    shell,
    keymap,
    indentWithTab,
    search,
    searchKeymap,
    highlightSelectionMatches,
    autocompletion,
    completionKeymap,
    closeBrackets,
    closeBracketsKeymap,
    vim,
    indentationMarkers,
    githubLight,
    githubDark,
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

const createStatusPanel = (vimEnabledRef) => {
    return (view) => {
        const dom = document.createElement('div');
        dom.className = 'cm-statusbar';

        const left = document.createElement('div');
        left.className = 'cm-statusbar-left';

        const right = document.createElement('div');
        right.className = 'cm-statusbar-right';

        dom.append(left, right);

        const update = () => {
            const state = view.state;
            const pos = state.selection.main.head;
            const line = state.doc.lineAt(pos);
            const col = pos - line.from + 1;
            const unit = state.facet(indentUnit) || '  ';
            const indentLabel = unit === '\t' ? 'Tabs' : `Spaces:${unit.length}`;
            left.textContent = `Ln ${line.number}, Col ${col}`;
            const vimLabel = vimEnabledRef.current ? 'Vim' : 'Insert';
            right.textContent = `${indentLabel} • ${vimLabel}`;
        };

        update();

        return {
            dom,
            update: (updateEvent) => {
                if (updateEvent.docChanged || updateEvent.selectionSet || updateEvent.viewportChanged) {
                    update();
                }
            },
            destroy: () => {},
        };
    };
};

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
    const paneRef = useRef(null);
    const initialContentRef = useRef(content || '');
    const [dirty, setDirty] = useState(false);

    const vimCompartment = useMemo(() => new Compartment(), []);
    const themeCompartment = useMemo(() => new Compartment(), []);

    const [vimEnabled, setVimEnabled] = useState(() => {
        try {
            return localStorage.getItem('vibes_vim_mode') === 'true';
        } catch {
            return false;
        }
    });
    const vimEnabledRef = useRef(vimEnabled);

    const [isDark, setIsDark] = useState(() => {
        try {
            return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        } catch {
            return false;
        }
    });

    useEffect(() => {
        if (!window.matchMedia) return;
        const media = window.matchMedia('(prefers-color-scheme: dark)');
        const onChange = () => setIsDark(media.matches);
        onChange();
        if (media.addEventListener) {
            media.addEventListener('change', onChange);
            return () => media.removeEventListener('change', onChange);
        }
        media.addListener(onChange);
        return () => media.removeListener(onChange);
    }, []);

    useEffect(() => {
        vimEnabledRef.current = vimEnabled;
        try {
            localStorage.setItem('vibes_vim_mode', vimEnabled ? 'true' : 'false');
        } catch {
            // ignore
        }
        const view = viewRef.current;
        if (!view) return;
        view.dispatch({
            effects: vimCompartment.reconfigure(vimEnabled ? vim() : []),
        });
    }, [vimEnabled, vimCompartment]);

    useEffect(() => {
        const view = viewRef.current;
        if (!view) return;
        view.dispatch({
            effects: themeCompartment.reconfigure(isDark ? githubDark : githubLight),
        });
    }, [isDark, themeCompartment]);

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
            highlightActiveLineGutter(),
            highlightSpecialChars(),
            EditorView.lineWrapping,
            scrollPastEnd(),
            indentOnInput(),
            closeBrackets(),
            autocompletion(),
            highlightSelectionMatches(),
            indentationMarkers(),
            syntaxHighlighting(headingStyle),
            syntaxHighlighting(classHighlighter),
            search(),
            vimCompartment.of(vimEnabled ? vim() : []),
            themeCompartment.of(isDark ? githubDark : githubLight),
            showPanel.of(createStatusPanel(vimEnabledRef)),
            keymap.of([
                ...searchKeymap,
                ...completionKeymap,
                ...closeBracketsKeymap,
                indentWithTab,
                { key: 'Mod-s', run: () => { handleSave(); return true; } },
            ]),
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

        const updateGutterWidth = () => {
            const pane = paneRef.current;
            const gutters = view.dom.querySelector('.cm-gutters');
            if (!pane || !gutters) return;
            const width = Math.max(32, Math.round(gutters.getBoundingClientRect().width));
            pane.style.setProperty('--cm-gutter-width', `${width}px`);
        };
        updateGutterWidth();
        window.addEventListener('resize', updateGutterWidth);

        return () => {
            window.removeEventListener('resize', updateGutterWidth);
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

    const handleToggleVim = useCallback(() => {
        setVimEnabled((prev) => !prev);
    }, []);

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

    return html`
        <div class="editor-pane" ref=${paneRef}>
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
                <button
                    class=${`editor-vim-toggle${vimEnabled ? ' active' : ''}`}
                    onClick=${handleToggleVim}
                    title="Toggle Vim mode"
                    aria-pressed=${vimEnabled ? 'true' : 'false'}
                >
                    Vim
                </button>
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
