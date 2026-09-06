import { html, useEffect, useRef, useState } from '../vendor/preact-htm.js';

export function SessionDeleteDialog({ name, onDelete, onClose }) {
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const cancel = useRef(null);
    const remove = useRef(null);
    useEffect(() => {
        const previous = document.activeElement;
        cancel.current?.focus();
        return () => { if (previous?.isConnected) previous.focus(); };
    }, []);
    const submit = async event => {
        event.preventDefault();
        if (busy) return;
        setBusy(true); setError('');
        try { await onDelete(); onClose(); }
        catch (err) { setError(err.message || 'Unable to delete session'); setBusy(false); }
    };
    const keys = event => {
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); if (!busy) onClose(); }
        if (event.key === 'Tab') {
            event.preventDefault();
            if (!busy) (document.activeElement === cancel.current ? remove : cancel).current?.focus();
        }
    };
    return html`<div class="rename-branch-overlay" onPointerDown=${event => { if (event.target === event.currentTarget && !busy) onClose(); }}>
        <form class="rename-branch-panel" role="alertdialog" aria-modal="true" aria-labelledby="session-delete-title" aria-describedby="session-delete-help" aria-busy=${busy} onSubmit=${submit} onKeyDown=${keys}>
            <h2 id="session-delete-title">Delete session</h2>
            <div id="session-delete-help">Delete “${name}”? Only empty sessions without children can be deleted. This cannot be undone.</div>
            ${error && html`<div role="alert">${error}</div>`}
            <div class="rename-branch-actions"><button ref=${remove} type="submit" disabled=${busy}>${busy ? 'Deleting…' : 'Delete'}</button><button ref=${cancel} type="button" disabled=${busy} onClick=${onClose}>Cancel</button></div>
        </form>
    </div>`;
}
