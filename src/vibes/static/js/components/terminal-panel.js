// Vibes host adapter; terminal DOM/rendering comes from deployed Piclaw 2.15.3.
import { html, useEffect, useRef, useState } from '../vendor/preact-htm.js';
import { terminalPaneExtension } from '../panes/terminal-pane.js';

export function TerminalPanel({ onClose, popout = false }) {
    const host = useRef(null);
    const pane = useRef(null);
    const [height, setHeight] = useState(() => Math.round(window.innerHeight * 0.45));
    const dragCleanup = useRef(null);
    const resize = (value) => {
        const next = Math.max(100, Math.min(window.innerHeight - 60, value));
        setHeight(next);
        requestAnimationFrame(() => window.dispatchEvent(new Event('dock-resize')));
    };
    const startResize = (event) => {
        if (event.button !== undefined && event.button !== 0) return;
        event.preventDefault();
        dragCleanup.current?.();
        const move = (e) => resize(window.innerHeight - e.clientY);
        const stop = () => {
            window.removeEventListener('pointermove', move);
            window.removeEventListener('pointerup', stop);
            window.removeEventListener('pointercancel', stop);
            dragCleanup.current = null;
        };
        window.addEventListener('pointermove', move);
        window.addEventListener('pointerup', stop);
        window.addEventListener('pointercancel', stop);
        dragCleanup.current = stop;
    };
    useEffect(() => {
        const fitViewport = () => resize(Math.min(height, window.innerHeight - 60));
        window.addEventListener('resize', fitViewport);
        return () => window.removeEventListener('resize', fitViewport);
    }, [height]);
    useEffect(() => {
        const token = new URL(location.href).searchParams.get('terminal_handoff');
        pane.current = terminalPaneExtension.mount(host.current, {
            transferState: token ? { handoffToken: token } : undefined,
        });
        if (token) {
            const url = new URL(location.href);
            url.searchParams.delete('terminal_handoff');
            history.replaceState(null, '', url);
        }
        return () => { dragCleanup.current?.(); pane.current?.dispose(); pane.current = null; };
    }, []);
    const detach = async () => {
        // Open synchronously for popup blockers, then request one-use handoff.
        const popup = window.open('about:blank', 'vibes-terminal');
        if (!popup) return;
        try {
            const transfer = await pane.current?.preparePopoutTransfer();
            if (!transfer?.terminal_handoff) { popup.close(); return; }
            const url = new URL(location.href);
            url.search = '';
            url.searchParams.set('terminal', '1');
            url.searchParams.set('terminal_handoff', transfer.terminal_handoff);
            popup.location.replace(url.href);
            onClose?.();
        } catch { popup.close(); }
    };
    return html`<div class="terminal-panel dock-panel standalone" role="region" aria-label="Terminal" style=${popout ? '' : `height:${height}px`}>
        ${!popout && html`<div class="dock-splitter" role="separator" aria-label="Resize terminal" aria-orientation="horizontal" aria-valuemin="100" aria-valuemax=${window.innerHeight - 60} aria-valuenow=${height} tabindex="0"
            onPointerDown=${startResize}
            onKeyDown=${(event) => {
                if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
                    event.preventDefault();
                    resize(height + (event.key === 'ArrowUp' ? 20 : -20));
                }
            }}></div>`}
        <div class="dock-panel-header">
            <span class="dock-panel-title">Terminal</span>
            <div class="dock-panel-actions">
                ${!popout && html`<button class="dock-panel-action" onClick=${detach} title="Open terminal in window" aria-label="Open terminal in window">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                        <path d="M15 3h6v6" /><path d="M10 14 21 3" /><path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5" />
                    </svg>
                </button>`}
                <button class="dock-panel-close" onClick=${onClose} title="Hide terminal" aria-label="Hide terminal">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M6 6l12 12M6 18L18 6" /></svg>
                </button>
            </div>
        </div>
        <div ref=${host} class="dock-panel-body"></div>
    </div>`;
}
