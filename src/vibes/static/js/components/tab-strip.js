import { html, useCallback, useEffect, useRef, useState } from '../vendor/preact-htm.js';

export function TabStrip({
    tabs,
    activeId,
    onActivate,
    onClose,
    onCloseOthers,
    onCloseAll,
    onTogglePin,
    onTogglePreview,
    previewTabs,
}) {
    const [contextMenu, setContextMenu] = useState(null);
    const stripRef = useRef(null);

    useEffect(() => {
        if (!contextMenu) return;
        const dismiss = (event) => {
            if (event.type === 'keydown' && event.key !== 'Escape') return;
            setContextMenu(null);
        };
        document.addEventListener('click', dismiss);
        document.addEventListener('keydown', dismiss);
        return () => {
            document.removeEventListener('click', dismiss);
            document.removeEventListener('keydown', dismiss);
        };
    }, [contextMenu]);

    useEffect(() => {
        const onKeyDown = (event) => {
            if (event.ctrlKey && event.key === 'Tab') {
                event.preventDefault();
                if (!tabs.length) return;
                const idx = tabs.findIndex((tab) => tab.id === activeId);
                if (idx < 0) return;
                const nextIdx = event.shiftKey
                    ? (idx - 1 + tabs.length) % tabs.length
                    : (idx + 1) % tabs.length;
                onActivate?.(tabs[nextIdx]?.id);
                return;
            }

            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'w' && activeId) {
                const editorPane = document.querySelector('.editor-pane');
                if (editorPane && editorPane.contains(document.activeElement)) {
                    event.preventDefault();
                    onClose?.(activeId);
                }
            }
        };
        document.addEventListener('keydown', onKeyDown);
        return () => document.removeEventListener('keydown', onKeyDown);
    }, [tabs, activeId, onActivate, onClose]);

    useEffect(() => {
        if (!activeId || !stripRef.current) return;
        stripRef.current.querySelector('.tab-item.active')?.scrollIntoView({
            block: 'nearest',
            inline: 'nearest',
            behavior: 'smooth',
        });
    }, [activeId]);

    const handleMouseDown = useCallback((event, id) => {
        if (event.button === 1) {
            event.preventDefault();
            onClose?.(id);
            return;
        }
        if (event.button === 0) {
            onActivate?.(id);
        }
    }, [onActivate, onClose]);

    const handleContextMenu = useCallback((event, id) => {
        event.preventDefault();
        setContextMenu({ id, x: event.clientX, y: event.clientY });
    }, []);

    const activeMenuTab = tabs.find((tab) => tab.id === contextMenu?.id);

    if (!tabs?.length) return null;

    return html`
        <div class="tab-strip" ref=${stripRef} role="tablist">
            ${tabs.map((tab) => html`
                <div
                    key=${tab.id}
                    class=${`tab-item${tab.id === activeId ? ' active' : ''}${tab.dirty ? ' dirty' : ''}${tab.pinned ? ' pinned' : ''}`}
                    role="tab"
                    aria-selected=${tab.id === activeId}
                    title=${tab.path}
                    onMouseDown=${(event) => handleMouseDown(event, tab.id)}
                    onContextMenu=${(event) => handleContextMenu(event, tab.id)}
                >
                    ${tab.pinned && html`
                        <span class="tab-pin-icon" aria-label="Pinned">
                            <svg viewBox="0 0 16 16" width="10" height="10" fill="currentColor">
                                <path d="M4.456.734a1.75 1.75 0 0 1 2.826.504l.613 1.327a3.1 3.1 0 0 0 2.084 1.707l2.454.584c1.332.317 1.8 1.972.832 2.94L11.06 10l3.72 3.72a.75.75 0 1 1-1.06 1.06L10 11.06l-2.204 2.205c-.968.968-2.623.5-2.94-.832l-.584-2.454a3.1 3.1 0 0 0-1.707-2.084l-1.327-.613a1.75 1.75 0 0 1-.504-2.826z" />
                            </svg>
                        </span>
                    `}
                    <span class="tab-label">${tab.label}</span>
                    <span
                        class="tab-close"
                        onClick=${(event) => { event.stopPropagation(); onClose?.(tab.id); }}
                        title=${tab.dirty ? 'Unsaved changes' : 'Close'}
                        aria-label=${tab.dirty ? 'Unsaved changes' : `Close ${tab.label}`}
                    >
                        ${tab.dirty
                            ? html`<span class="tab-dirty-dot" aria-hidden="true"></span>`
                            : html`<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
                                <line x1="4" y1="4" x2="12" y2="12" />
                                <line x1="12" y1="4" x2="4" y2="12" />
                            </svg>`}
                    </span>
                </div>
            `)}
        </div>
        ${contextMenu && html`
            <div class="tab-context-menu" style=${{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }}>
                <button onClick=${() => { onClose?.(contextMenu.id); setContextMenu(null); }}>Close</button>
                <button onClick=${() => { onCloseOthers?.(contextMenu.id); setContextMenu(null); }}>Close Others</button>
                <button onClick=${() => { onCloseAll?.(); setContextMenu(null); }}>Close All</button>
                <hr />
                <button onClick=${() => { onTogglePin?.(contextMenu.id); setContextMenu(null); }}>
                    ${activeMenuTab?.pinned ? 'Unpin' : 'Pin'}
                </button>
                ${activeMenuTab?.isMarkdown && html`
                    <hr />
                    <button onClick=${() => { onTogglePreview?.(contextMenu.id); setContextMenu(null); }}>
                        ${previewTabs?.has(contextMenu.id) ? 'Hide Preview' : 'Preview'}
                    </button>
                `}
            </div>
        `}
    `;
}
