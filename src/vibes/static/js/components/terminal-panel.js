// Vibes host adapter; terminal DOM/rendering comes from deployed Piclaw 2.15.3.
import { html, useEffect, useRef } from '../vendor/preact-htm.js';
import { terminalPaneExtension } from '../panes/terminal-pane.js';

export function TerminalPanel({ onClose, popout = false }) {
    const host = useRef(null);
    const pane = useRef(null);
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
        return () => { pane.current?.dispose(); pane.current = null; };
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
    return html`<section class="terminal-panel" aria-label="Terminal">
        <div class="terminal-panel-toolbar">
            <span>Terminal</span>
            ${!popout && html`<button onClick=${detach} title="Open terminal in window">Open in Window</button>`}
            <button onClick=${onClose} title="Close terminal">Close</button>
        </div>
        <div ref=${host} class="terminal-panel-host" style="height:100%;min-height:0;flex:1"></div>
    </section>`;
}
