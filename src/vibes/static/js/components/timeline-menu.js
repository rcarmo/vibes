import { html, useEffect, useLayoutEffect, useRef, useState } from '../vendor/preact-htm.js';

// Piclaw-compatible shell menu exposing only actions implemented by this host.
export function TimelineMenu({ workspaceOpen, onToggleWorkspace, onOpenTerminal, onOpenQuickActions }) {
    const [open, setOpen] = useState(false);
    const button = useRef(null);
    const menu = useRef(null);
    const close = (restore = false) => {
        setOpen(false);
        if (restore) requestAnimationFrame(() => button.current?.focus());
    };
    const run = (action, restoreTarget = false) => {
        close();
        if (restoreTarget) button.current?.focus({ preventScroll: true });
        action?.();
    };
    useEffect(() => { close(); }, [workspaceOpen]);
    useLayoutEffect(() => {
        if (!open) return;
        const pointer = event => {
            if (button.current?.contains(event.target) || menu.current?.contains(event.target)) return;
            close(false);
        };
        const key = event => {
            if (event.key !== 'Escape') return;
            event.preventDefault(); event.stopPropagation(); close(true);
        };
        document.addEventListener('pointerdown', pointer, true);
        document.addEventListener('keydown', key, true);
        return () => {
            document.removeEventListener('pointerdown', pointer, true);
            document.removeEventListener('keydown', key, true);
        };
    }, [open]);
    return html`<div class=${`timeline-menu-portal ${workspaceOpen ? 'in-workspace' : 'in-chat'}`} style="top:max(8px, env(safe-area-inset-top));left:8px;right:auto">
        <button ref=${button} class=${`timeline-menu-btn${open ? ' active' : ''}`} data-testid="hamburger"
            type="button" title="Workspace menu" aria-label="Workspace menu" aria-haspopup="menu"
            aria-expanded=${open ? 'true' : 'false'} onClick=${() => setOpen(value => !value)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
                <line x1="4" y1="7" x2="20" y2="7"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="17" x2="20" y2="17"/>
            </svg>
        </button>
        ${open && html`<div ref=${menu} class="workspace-menu-dropdown timeline-menu-dropdown" role="menu">
            <button class="workspace-menu-item" role="menuitem" onClick=${() => run(onToggleWorkspace)}>${workspaceOpen ? 'Hide workspace' : 'Show workspace'}</button>
            ${!workspaceOpen && html`<button class="workspace-menu-item" role="menuitem" onClick=${() => run(onToggleWorkspace)}>Open explorer</button>`}
            ${onOpenQuickActions && html`<button class="workspace-menu-item" role="menuitem" onClick=${() => run(onOpenQuickActions, true)}>Quick actions</button>`}
            ${onOpenTerminal && html`<button class="workspace-menu-item" role="menuitem" onClick=${() => run(onOpenTerminal)}>Open terminal</button>`}
        </div>`}
    </div>`;
}
