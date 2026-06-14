import { html, useCallback, useEffect, useMemo, useRef, useState } from '../vendor/preact-htm.js';

const OFFICE_EXTENSIONS = /\.(docx?|xlsx?|pptx?|odt|ods|odp|rtf)$/i;
const CSV_EXTENSIONS = /\.(csv|tsv)$/i;
const PDF_EXTENSIONS = /\.pdf$/i;
const IMAGE_EXTENSIONS = /\.(png|jpe?g|gif|webp|bmp|ico|svg)$/i;
const DRAWIO_EXTENSIONS = /\.drawio(\.xml|\.svg|\.png)?$/i;
const HTML_EXTENSIONS = /\.html?$/i;
const VIDEO_EXTENSIONS = /\.(mp4|webm|mov|ogv|avi|mkv)$/i;

export interface EditorTab {
    id: string;
    path?: string;
    label?: string;
    dirty?: boolean;
    pinned?: boolean;
}

export interface StandaloneTabOptions {
    hasPopOutTab?: boolean;
}

export interface TabStripProps {
    tabs?: EditorTab[];
    activeId?: string | null;
    onActivate?: (id: string) => void;
    onClose?: (id: string) => void;
    onCloseOthers?: (id: string) => void;
    onCloseAll?: () => void;
    onTogglePin?: (id: string) => void;
    onTogglePreview?: (id: string) => void;
    previewTabs?: Set<string>;
    onPopOutTab?: (id: string, label?: string) => void;
    onToggleDock?: () => void;
    dockVisible?: boolean;
    onToggleZen?: () => void;
    zenMode?: boolean;
}

interface ContextMenuState {
    id: string;
    x: number;
    y: number;
}

/**
 * Resolve a standalone (new-tab) URL for a given file path, or null if the
 * file type should be opened inside the pane system instead.
 */
export function getStandaloneTabUrl(path: unknown, { hasPopOutTab = false }: StandaloneTabOptions = {}): string | null {
    const normalizedPath = typeof path === 'string' ? path.trim() : '';
    if (!normalizedPath) return null;
    if (OFFICE_EXTENSIONS.test(normalizedPath)) {
        const rawUrl = '/workspace/raw?path=' + encodeURIComponent(normalizedPath);
        const name = normalizedPath.split('/').pop() || 'document';
        return '/office-viewer/?url=' + encodeURIComponent(rawUrl) + '&name=' + encodeURIComponent(name);
    }
    if (CSV_EXTENSIONS.test(normalizedPath)) {
        return '/csv-viewer/?path=' + encodeURIComponent(normalizedPath);
    }
    if (PDF_EXTENSIONS.test(normalizedPath)) {
        return '/pdf-viewer/?path=' + encodeURIComponent(normalizedPath);
    }
    if (HTML_EXTENSIONS.test(normalizedPath)) {
        return '/html-viewer/?path=' + encodeURIComponent(normalizedPath);
    }
    if (VIDEO_EXTENSIONS.test(normalizedPath)) {
        return '/video-viewer/?path=' + encodeURIComponent(normalizedPath);
    }
    if (IMAGE_EXTENSIONS.test(normalizedPath) && !DRAWIO_EXTENSIONS.test(normalizedPath)) {
        return '/image-viewer/?path=' + encodeURIComponent(normalizedPath);
    }
    if (DRAWIO_EXTENSIONS.test(normalizedPath) && !hasPopOutTab) {
        return '/drawio/edit?path=' + encodeURIComponent(normalizedPath);
    }
    return null;
}

/**
 * TabStrip — horizontal tab bar for open editor files.
 */
export function TabStrip({
    tabs = [],
    activeId,
    onActivate,
    onClose,
    onCloseOthers,
    onCloseAll,
    onTogglePin,
    onTogglePreview,
    previewTabs,
    onPopOutTab,
    onToggleDock,
    dockVisible,
    onToggleZen,
    zenMode,
}: TabStripProps) {
    const [contextMenu, setContextMenu] = useState(null as ContextMenuState | null);
    const stripRef = useRef(null);

    // Close context menu on outside click or Escape.
    useEffect(() => {
        if (!contextMenu) return;
        const dismiss = (event: MouseEvent | KeyboardEvent) => {
            if (event.type === 'keydown' && (event as KeyboardEvent).key !== 'Escape') return;
            setContextMenu(null);
        };
        document.addEventListener('click', dismiss);
        document.addEventListener('keydown', dismiss);
        return () => {
            document.removeEventListener('click', dismiss);
            document.removeEventListener('keydown', dismiss);
        };
    }, [contextMenu]);

    // Keyboard shortcuts: Ctrl+Tab (next), Ctrl+Shift+Tab (prev), Ctrl+W (close).
    useEffect(() => {
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.ctrlKey && event.key === 'Tab') {
                event.preventDefault();
                if (!tabs.length) return;
                const idx = tabs.findIndex((tab) => tab.id === activeId);
                if (event.shiftKey) {
                    const prev = tabs[(idx - 1 + tabs.length) % tabs.length];
                    if (prev) onActivate?.(prev.id);
                } else {
                    const next = tabs[(idx + 1) % tabs.length];
                    if (next) onActivate?.(next.id);
                }
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

    // Scroll active tab into view.
    useEffect(() => {
        const stripEl = stripRef.current as HTMLElement | null;
        if (!activeId || !stripEl) return;
        stripEl.querySelector('.tab-item.active')?.scrollIntoView({
            block: 'nearest',
            inline: 'nearest',
            behavior: 'smooth',
        });
    }, [activeId]);

    // Middle-click closes immediately so the tab never becomes active.
    const handleTabMouseDown = useCallback((event: MouseEvent, id: string) => {
        if (event.button === 1) {
            event.preventDefault();
            onClose?.(id);
        }
    }, [onClose]);

    const handleTabClick = useCallback((event: MouseEvent, id: string) => {
        if (event.defaultPrevented) return;
        if (event.button === 0) {
            onActivate?.(id);
        }
    }, [onActivate]);

    const handleContextMenu = useCallback((event: MouseEvent, id: string) => {
        event.preventDefault();
        setContextMenu({ id, x: event.clientX, y: event.clientY });
    }, []);

    // Keep close-button pointer presses isolated from the parent tab so the
    // tab never activates before the close click lands.
    const handleClosePointerDown = useCallback((event: Event) => {
        event.preventDefault();
        event.stopPropagation();
    }, []);

    const handleCloseClick = useCallback((event: MouseEvent, id: string) => {
        event.preventDefault();
        event.stopPropagation();
        onClose?.(id);
    }, [onClose]);

    const contextMenuTab = useMemo(
        () => tabs.find((tab) => tab.id === contextMenu?.id) || null,
        [contextMenu?.id, tabs],
    );
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
                    onMouseDown=${(event: MouseEvent) => handleTabMouseDown(event, tab.id)}
                    onClick=${(event: MouseEvent) => handleTabClick(event, tab.id)}
                    onContextMenu=${(event: MouseEvent) => handleContextMenu(event, tab.id)}
                >
                    ${tab.pinned && html`
                        <span class="tab-pin-icon" aria-label="Pinned">
                            <svg viewBox="0 0 16 16" width="10" height="10" fill="currentColor">
                                <path d="M4.456.734a1.75 1.75 0 0 1 2.826.504l.613 1.327a3.1 3.1 0 0 0 2.084 1.707l2.454.584c1.332.317 1.8 1.972.832 2.94L11.06 10l3.72 3.72a.75.75 0 1 1-1.06 1.06L10 11.06l-2.204 2.205c-.968.968-2.623.5-2.94-.832l-.584-2.454a3.1 3.1 0 0 0-1.707-2.084l-1.327-.613a1.75 1.75 0 0 1-.504-2.826z" />
                            </svg>
                        </span>
                    `}
                    <span class="tab-label">${tab.label}</span>
                    <button
                        type="button"
                        class="tab-close"
                        onPointerDown=${handleClosePointerDown}
                        onMouseDown=${handleClosePointerDown}
                        onClick=${(event: MouseEvent) => handleCloseClick(event, tab.id)}
                        title=${tab.dirty ? 'Unsaved changes' : 'Close'}
                        aria-label=${tab.dirty ? 'Unsaved changes' : `Close ${tab.label}`}
                    >
                        ${tab.dirty
                            ? html`<span class="tab-dirty-dot" aria-hidden="true"></span>`
                            : html`<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true" focusable="false" style=${{ pointerEvents: 'none' }}>
                                <line x1="4" y1="4" x2="12" y2="12" style=${{ pointerEvents: 'none' }} />
                                <line x1="12" y1="4" x2="4" y2="12" style=${{ pointerEvents: 'none' }} />
                            </svg>`}
                    </button>
                </div>
            `)}
            ${onToggleDock && html`
                <div class="tab-strip-spacer"></div>
                <button
                    class=${`tab-strip-dock-toggle${dockVisible ? ' active' : ''}`}
                    onClick=${onToggleDock}
                    title=${`${dockVisible ? 'Hide' : 'Show'} terminal (Ctrl+\`)`}
                    aria-label=${`${dockVisible ? 'Hide' : 'Show'} terminal`}
                    aria-pressed=${dockVisible ? 'true' : 'false'}
                >
                    <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="1.75" y="2.25" width="12.5" height="11.5" rx="2"/>
                        <polyline points="4.5 5.25 7 7.75 4.5 10.25"/>
                        <line x1="8.5" y1="10.25" x2="11.5" y2="10.25"/>
                    </svg>
                </button>
            `}
            ${onToggleZen && html`
                <button
                    class=${`tab-strip-zen-toggle${zenMode ? ' active' : ''}`}
                    onClick=${onToggleZen}
                    title=${`${zenMode ? 'Exit' : 'Enter'} zen mode (Ctrl+Shift+Z)`}
                    aria-label=${`${zenMode ? 'Exit' : 'Enter'} zen mode`}
                    aria-pressed=${zenMode ? 'true' : 'false'}
                >
                    <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        ${zenMode
                            ? html`<polyline points="4 8 1.5 8 1.5 1.5 14.5 1.5 14.5 8 12 8"/><polyline points="4 8 1.5 8 1.5 14.5 14.5 14.5 14.5 8 12 8"/>`
                            : html`<polyline points="5.5 1.5 1.5 1.5 1.5 5.5"/><polyline points="10.5 1.5 14.5 1.5 14.5 5.5"/><polyline points="5.5 14.5 1.5 14.5 1.5 10.5"/><polyline points="10.5 14.5 14.5 14.5 14.5 10.5"/>`
                        }
                    </svg>
                </button>
            `}
        </div>
        ${contextMenu && html`
            <div class="tab-context-menu" style=${{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }}>
                <button onClick=${() => { onClose?.(contextMenu.id); setContextMenu(null); }}>Close</button>
                <button onClick=${() => { onCloseOthers?.(contextMenu.id); setContextMenu(null); }}>Close Others</button>
                <button onClick=${() => { onCloseAll?.(); setContextMenu(null); }}>Close All</button>
                <hr />
                <button onClick=${() => { onTogglePin?.(contextMenu.id); setContextMenu(null); }}>
                    ${contextMenuTab?.pinned ? 'Unpin' : 'Pin'}
                </button>
                ${onPopOutTab && html`
                    <button onClick=${() => {
                        const tab = tabs.find((t) => t.id === contextMenu.id);
                        onPopOutTab(contextMenu.id, tab?.label);
                        setContextMenu(null);
                    }}>Open in Window</button>
                `}
                ${onTogglePreview && /\.(md|mdx|markdown)$/i.test(contextMenu.id) && html`
                    <hr />
                    <button onClick=${() => { onTogglePreview(contextMenu.id); setContextMenu(null); }}>
                        ${previewTabs?.has(contextMenu.id) ? 'Hide Preview' : 'Preview'}
                    </button>
                `}
                ${(() => {
                    const standaloneUrl = getStandaloneTabUrl(contextMenu.id, {
                        hasPopOutTab: typeof onPopOutTab === 'function',
                    });
                    if (!standaloneUrl) return null;
                    return html`
                        <hr />
                        <button onClick=${() => {
                            window.open(standaloneUrl, '_blank', 'noopener');
                            setContextMenu(null);
                        }}>Open in New Tab</button>
                    `;
                })()}
            </div>
        `}
    `;
}
