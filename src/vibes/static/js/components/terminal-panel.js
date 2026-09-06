// Vibes host adapter; terminal DOM/rendering comes from deployed Piclaw 2.15.3.
import { html, useEffect, useRef, useState } from '../vendor/preact-htm.js';
import { terminalPaneExtension } from '../panes/terminal-pane.js';

export function TerminalPanel({ onClose, popout = false, shared = false }) {
    const host = useRef(null);
    const pane = useRef(null);
    const popupRef = useRef(null);
    const pendingPopup = useRef(null);
    const [detached, setDetached] = useState(false);
    const [transferError, setTransferError] = useState('');
    const transferPending = useRef(false);
    const mounted = useRef(true);
    const [transferring, setTransferring] = useState(false);
    const [height, setHeight] = useState(() => Math.round(window.innerHeight * 0.45));
    const dragCleanup = useRef(null);
    const maxHeight = () => Math.max(100, (host.current?.closest('.editor-pane-container')?.clientHeight || window.innerHeight) - 60);
    const resize = (value) => {
        const next = Math.max(100, Math.min(maxHeight(), value));
        setHeight(next);
        requestAnimationFrame(() => window.dispatchEvent(new Event('dock-resize')));
    };
    const startResize = (event) => {
        if (event.button !== undefined && event.button !== 0) return;
        event.preventDefault();
        dragCleanup.current?.();
        const move = (e) => resize((host.current?.closest('.editor-pane-container')?.getBoundingClientRect().bottom || window.innerHeight) - e.clientY);
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
    }, [height, shared]);
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
        return () => { mounted.current = false; pendingPopup.current?.close(); pendingPopup.current = null; dragCleanup.current?.(); pane.current?.dispose(); pane.current = null; };
    }, []);
    const detach = async () => {
        if (transferPending.current) return;
        // Open synchronously for popup blockers, then request one-use handoff.
        const popup = window.open('about:blank', 'vibes-terminal');
        if (!popup) return;
        pendingPopup.current = popup;
        transferPending.current = true; setTransferring(true);
        try {
            const transfer = await pane.current?.preparePopoutTransfer();
            if (!mounted.current || !transfer?.terminal_handoff) { popup.close(); return; }
            const url = new URL(location.href);
            url.search = '';
            url.searchParams.set('terminal', '1');
            url.searchParams.set('terminal_handoff', transfer.terminal_handoff);
            popup.location.replace(url.href);
            popupRef.current = popup;
            pendingPopup.current = null;
            pane.current?.dispose();
            pane.current = null;
            setDetached(true);
            setTransferError('');
        } catch { popup.close(); setTransferError('Unable to detach terminal.'); }
        finally { pendingPopup.current = null; transferPending.current = false; setTransferring(false); }
    };
    const reattach = async () => {
        if (transferPending.current) return;
        transferPending.current = true; setTransferring(true);
        try {
            let token = null;
            let restarted = false;
            if (popupRef.current?.closed) {
                // Detached sessions can reconnect without handoff. Never bypass
                // ownership checks: the server rejects an active second client.
                const response = await fetch('/terminal/session', { credentials: 'same-origin' });
                const session = await response.json();
                if (!response.ok || !session.enabled || session.connected_clients) throw new Error('Still connected');
                restarted = !session.active;
            } else {
                const response = await fetch('/terminal/handoff', { method: 'POST', credentials: 'same-origin' });
                const result = await response.json();
                if (!response.ok || !result.handoff?.token) throw new Error('No handoff');
                token = result.handoff.token;
            }
            if (!mounted.current) return;
            pane.current = terminalPaneExtension.mount(host.current, {
                transferState: token ? { handoffToken: token } : undefined,
            });
            setDetached(false);
            setTransferError(restarted ? 'Previous terminal session expired; started a new shell.' : '');
            popupRef.current?.close();
            popupRef.current = null;
            requestAnimationFrame(() => window.dispatchEvent(new Event('dock-resize')));
        } catch { setTransferError('Unable to reattach. Check that the terminal window is connected.'); }
        finally { transferPending.current = false; setTransferring(false); }
    };
    return html`<div class=${`terminal-panel dock-panel${shared ? '' : ' standalone'}`} role="region" aria-label="Terminal" style=${popout ? '' : `height:${height}px`}>
        ${!popout && shared && html`<div class="dock-splitter" role="separator" aria-label="Resize terminal" aria-orientation="horizontal" aria-valuemin="100" aria-valuemax=${maxHeight()} aria-valuenow=${height} tabindex="0"
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
                ${!popout && !detached && html`<button class="dock-panel-action" disabled=${transferring} onClick=${detach} title="Open terminal in window" aria-label="Open terminal in window">
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 3H3v10h10v-3" /><path d="M9 3h4v4" /><path d="M8 8l5-5" /></svg>
                </button>`}
                ${detached && html`<button type="button" class="dock-panel-action" title="Reattach terminal" aria-label="Reattach terminal" disabled=${transferring} onClick=${reattach}><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6V3h10v10h-3" /><path d="M3 9v4h4" /><path d="M3 13l5-5" /></svg></button>`}
                <button class="dock-panel-close" onClick=${onClose} title="Hide terminal" aria-label="Hide terminal">
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" /></svg>
                </button>
            </div>
        </div>
        ${transferError && html`<div role="alert">${transferError}</div>`}
        ${detached && html`<div class="dock-panel-body dock-panel-body-detached">
            <div class="editor-empty-state pane-detached-state">
                <h3>Terminal detached</h3>
                <p>This terminal is open in another window.</p>
                <button type="button" class="editor-empty-action" disabled=${transferring} onClick=${reattach}>Reattach here</button>
            </div>
        </div>`}
        <div ref=${host} class="dock-panel-body" style=${detached ? 'display:none' : ''}></div>
    </div>`;
}
