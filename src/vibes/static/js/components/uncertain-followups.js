import { html, useState } from '../vendor/preact-htm.js';

export function UncertainFollowups({ items = [], onDiscard }) {
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    if (!items.length) return null;
    async function discard(item) {
        if (busy || !window.confirm('Discard this uncertain item? It may already have run. This will not retry it.')) return;
        setBusy(true);
        setError('');
        try {
            await onDiscard(item.row_id);
        } catch {
            setError('Could not discard item. Refresh and review again.');
        } finally {
            setBusy(false);
        }
    }
    return html`<section aria-label="Uncertain follow-ups">
        <h3>Uncertain follow-ups</h3>
        <p>These items may already have run. They will not be retried automatically.</p>
        ${items.map(item => html`<div key=${item.row_id}>
            <p>${item.content}</p>
            <button type="button" disabled=${busy} onClick=${() => discard(item)}>Discard without retry</button>
        </div>`)}
        ${error && html`<p role="alert">${error}</p>`}
    </section>`;
}
