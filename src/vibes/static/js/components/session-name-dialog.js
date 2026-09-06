import { html, useEffect, useRef, useState } from '../vendor/preact-htm.js';

export function SessionNameDialog({ name, onSave, onClose, creating = false, parentName = null }) {
    const [value, setValue] = useState(name || '');
    const [busy, setBusy] = useState(false);
    const pending = useRef(false);
    const [error, setError] = useState('');
    const input = useRef(null);
    const panel = useRef(null);
    const valid = !!value.trim() && value.trim().length <= 80 && !/[\x00-\x1f\x7f]/.test(value);
    useEffect(() => {
        const previous = document.activeElement;
        input.current?.focus(); input.current?.select();
        return () => { if (previous?.isConnected) previous.focus(); };
    }, []);
    const submit = async event => {
        event.preventDefault();
        if (!valid || pending.current) return;
        pending.current = true;
        setBusy(true); setError('');
        try { await onSave(value.trim()); onClose(); }
        catch (err) { setError(err.message || 'Unable to save session'); setBusy(false); pending.current = false; }
    };
    const keys = event => {
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); if (!busy) onClose(); }
        if (event.key !== 'Tab') return;
        const items = [...panel.current.querySelectorAll('input:not(:disabled), button:not(:disabled)')];
        const first = items[0], last = items.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    return html`<div class="rename-branch-overlay" onPointerDown=${event => { if (event.target === event.currentTarget && !busy) onClose(); }}>
        <form ref=${panel} class="rename-branch-panel" role="dialog" aria-modal="true" aria-labelledby="session-name-title" aria-busy=${busy} onSubmit=${submit} onKeyDown=${keys}>
            <h2 id="session-name-title">${creating ? 'New session' : 'Rename session'}</h2>
            <input ref=${input} class="rename-branch-input" aria-label="Session name" aria-describedby="session-name-help" value=${value} disabled=${busy} onInput=${event => setValue(event.target.value)} />
            <div id="session-name-help" class="rename-branch-help">Use 1–80 characters without control characters.${creating && parentName !== null && html`<p>Creates an empty child of “${parentName}”. Conversation history is not copied.</p>`}</div>
            ${error && html`<div role="alert">${error}</div>`}
            <div class="rename-branch-actions"><button class="rename-branch-save" type="submit" disabled=${!valid || busy}>${busy ? (creating ? 'Creating…' : 'Renaming…') : (creating ? 'Create' : 'Save')}</button><button class="rename-branch-cancel" type="button" disabled=${busy} onClick=${onClose}>Cancel</button></div>
        </form>
    </div>`;
}
