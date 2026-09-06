// Registry adapter using deployed Piclaw classic picker class/role structure.
import { groupSessions } from './session-groups.js';
import { html, useState, useMemo, useEffect, useRef } from '../vendor/preact-htm.js';

export function SessionPicker({ sessions = [], currentId = 'default', onSelect, onClose, onCreate, onRename, onDelete, onPin, onArchive }) {
    const [query, setQuery] = useState('');
    const [index, setIndex] = useState(0);
    const [error, setError] = useState('');
    const search = useRef(null);
    const groups = useMemo(() => groupSessions(sessions, currentId).map(group => ({ ...group, items: group.items.filter(item => `${item.name} ${item.id}`.toLowerCase().includes(query.toLowerCase())) })).filter(group => group.items.length), [sessions, currentId, query]);
    const matches = groups.flatMap(group => group.items);
    const selectedIndex = Math.max(0, Math.min(index, matches.length - 1));
    useEffect(() => { search.current?.focus(); }, []);

    const act = async fn => { try { setError(''); await fn?.(); } catch (err) { setError(err.message || 'Session action failed'); } };
    const keys = event => {
        if (event.key === 'Escape') { event.preventDefault(); onClose?.(); }
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            setIndex(value => Math.max(0, Math.min(matches.length - 1, Math.min(value, matches.length - 1) + (event.key === 'ArrowDown' ? 1 : -1))));
        }
        if (event.target?.closest('button')) return;
        if (event.key === 'Enter' && matches[selectedIndex]) {
            event.preventDefault();
            act(() => onSelect?.(matches[selectedIndex].id));
        }
    };
    return html`<div class="compose-model-popup compose-session-popup" data-testid="session-popup" onKeyDown=${keys}>
        <div class="compose-session-popup-header"><input ref=${search} class="compose-session-search" type="search" value=${query} onInput=${e => { setQuery(e.target.value); setIndex(0); }} placeholder="Search sessions" aria-label="Search sessions" /></div>
        ${error && html`<div role="alert">${error}</div>`}
        <div class="compose-model-popup-menu compose-session-popup-results" role="listbox" aria-label="Sessions" aria-activedescendant=${matches[selectedIndex] ? `session-option-${matches[selectedIndex].id}` : undefined}>
            ${groups.map(group => html`<div class="session-popup-group" role="group" aria-label=${group.label}>
                <div class="compose-session-section-heading">${group.label}</div>
                ${group.items.map(item => html`<div key=${item.id} class=${`compose-model-option-row${item.id === currentId ? ' active' : ''}${matches[selectedIndex]?.id === item.id ? ' keyboard-active' : ''}`}>
                <button type="button" class=${`compose-model-pin-toggle${item.pinned ? ' pinned' : ''}`} aria-label=${item.pinned ? 'Unpin session' : 'Pin session'} aria-pressed=${!!item.pinned} onClick=${() => act(() => onPin?.(item.id, !item.pinned))}>☆</button>
                <button type="button" id=${`session-option-${item.id}`} class="compose-model-option compose-model-option-session" role="option" aria-selected=${item.id === currentId} onClick=${() => act(() => onSelect?.(item.id))}>
                    <span class="compose-session-row-content"><span class="compose-session-row-label">${item.name}</span><span class="compose-session-row-meta">${item.id}</span><span class="compose-session-row-meta">${item.message_count ?? 0} messages</span></span>
                    <span class=${`compose-session-status-pill ${item.archived ? 'closed' : item.is_running ? 'active' : 'idle'}`}>${item.archived ? 'Archived' : item.is_running ? 'Running' : 'Idle'}</span>
                </button>
                <button type="button" aria-label=${`Rename ${item.name}`} onClick=${() => act(() => onRename?.(item.id))}>Rename</button>
                ${item.id !== 'default' && onArchive && html`<button type="button" aria-label=${`${item.archived ? 'Restore' : 'Archive'} ${item.name}`} onClick=${() => act(() => onArchive(item.id, !item.archived))}>${item.archived ? 'Restore' : 'Archive'}</button>`}
                ${item.id !== 'default' && html`<button type="button" aria-label=${`Delete ${item.name}`} disabled=${!!item.message_count} onClick=${() => act(() => onDelete?.(item.id))}>Delete</button>`}
            </div>`)}
            </div>`)}
        </div>
        <button type="button" onClick=${() => act(onCreate)}>New session</button>
    </div>`;
}
