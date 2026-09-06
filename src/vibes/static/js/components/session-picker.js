// Registry adapter using deployed Piclaw classic picker class/role structure.
import { html, useState, useMemo, useEffect, useRef } from '../vendor/preact-htm.js';

export function SessionPicker({ sessions = [], currentId = 'default', onSelect, onClose, onCreate, onRename, onDelete, onPin }) {
    const [query, setQuery] = useState('');
    const [index, setIndex] = useState(0);
    const [error, setError] = useState('');
    const search = useRef(null);
    const matches = useMemo(() => sessions.filter(item => `${item.name} ${item.id}`.toLowerCase().includes(query.toLowerCase())), [sessions, query]);
    useEffect(() => { search.current?.focus(); }, []);

    const act = async fn => { try { setError(''); await fn?.(); } catch (err) { setError(err.message || 'Session action failed'); } };
    const keys = event => {
        if (event.key === 'Escape') { event.preventDefault(); onClose?.(); }
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            setIndex(value => Math.max(0, Math.min(matches.length - 1, value + (event.key === 'ArrowDown' ? 1 : -1))));
        }
        if (event.target?.closest('button')) return;
        if (event.key === 'Enter' && matches[index]) {
            event.preventDefault();
            act(() => onSelect?.(matches[index].id));
        }
    };
    return html`<div class="model-popup session-popup" data-testid="session-popup" onKeyDown=${keys}>
        <div class="session-popup-search-wrap"><input ref=${search} class="session-popup-search" type="search" value=${query} onInput=${e => { setQuery(e.target.value); setIndex(0); }} placeholder="Search sessions" aria-label="Search sessions" /></div>
        ${error && html`<div role="alert">${error}</div>`}
        <div class="session-popup-results" role="listbox" aria-label="Sessions" aria-activedescendant=${matches[index] ? `session-option-${matches[index].id}` : undefined}>
            ${matches.map((item, position) => html`<div key=${item.id} class=${`session-option-row${item.id === currentId ? ' active' : ''}${position === index ? ' keyboard-active' : ''}`}>
                <button type="button" class=${`session-pin-toggle${item.pinned ? ' pinned' : ''}`} aria-label=${item.pinned ? 'Unpin session' : 'Pin session'} aria-pressed=${!!item.pinned} onClick=${() => act(() => onPin?.(item.id, !item.pinned))}>☆</button>
                <button type="button" id=${`session-option-${item.id}`} class="model-option session-option" role="option" aria-selected=${item.id === currentId} onClick=${() => act(() => onSelect?.(item.id))}>
                    <span class="session-option-main"><span class="model-option-name session-option-name">${item.name}</span><span class="model-option-id">${item.id}</span><span class="session-option-metrics">${item.message_count ?? 0} messages</span></span>
                </button>
                <button type="button" aria-label=${`Rename ${item.name}`} onClick=${() => act(() => onRename?.(item.id))}>Rename</button>
                ${item.id !== 'default' && html`<button type="button" aria-label=${`Delete ${item.name}`} disabled=${!!item.message_count} onClick=${() => act(() => onDelete?.(item.id))}>Delete</button>`}
            </div>`)}
        </div>
        <button type="button" onClick=${() => act(onCreate)}>New session</button>
    </div>`;
}
