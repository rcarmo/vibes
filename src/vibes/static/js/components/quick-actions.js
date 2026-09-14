// Applicable Piclaw classic 3.1.2 timeline quick actions. CSS is vendored in
// classic/chat.css; actions are provided by the host, never guessed from labels.
import { html, useEffect, useLayoutEffect, useMemo, useRef, useState } from '../vendor/preact-htm.js';
import { getAgentCommands } from '../api.js';

export function shouldOpenQuickActions(event) {
    if (event.defaultPrevented || event.isComposing || event.repeat || event.ctrlKey || event.metaKey || event.altKey) return false;
    if (typeof event.key !== 'string' || [...event.key].length !== 1 || !/\S/u.test(event.key)) return false;
    const target = event.target;
    if (target?.isContentEditable || target?.closest?.('input, textarea, select, button, a, [contenteditable="true"], .compose-box, .workspace-sidebar, .workspace-explorer, .editor-pane-container, .dock-panel, dialog, [role="dialog"], .rename-branch-overlay, .agent-request-modal, .attachment-preview-modal, .model-settings-dialog')) return false;
    return !target || ['BODY', 'HTML'].includes(target.tagName)
        || Boolean(target.closest?.('.container, .timeline, .post, .post-body, .post-content, .agent-status-panel'));
}

const normalise = text => String(text || '').toLowerCase().replace(/^[@/]+/, '').replace(/\s+/g, ' ').trim();
export function quickActionItems({ sessions = [], commands = [], workspace = [], query = '' }) {
    const seen = new Set();
    const items = [];
    const add = item => {
        if (seen.has(item.key)) return;
        seen.add(item.key);
        if (normalise(`${item.title} ${item.subtitle}`).includes(normalise(query))) items.push(item);
    };
    for (const session of sessions) {
        if (session.archived || !session.id) continue;
        add({ key: `session:${session.id}`, kind: 'agent', title: `@${session.name || session.id}`, subtitle: session.id,
            hint: 'Open', visual: '@', sessionId: session.id });
    }
    for (const action of workspace) {
        if (typeof action.run !== 'function') continue;
        add({ key: `workspace:${action.id}`, kind: 'workspace', hint: 'Run', visual: '›', ...action });
    }
    for (const command of commands) {
        if (typeof command?.name !== 'string' || !command.name.trim().replace(/^\/+/, '')) continue;
        const name = '/' + command.name.trim().replace(/^\/+/, '');
        add({ key: `slash:${name.toLowerCase()}`, kind: 'slash', title: name,
            subtitle: command.description || '', hint: 'Insert', visual: '/', commandName: name });
    }
    return items;
}

function preferredIndex(items, query) {
    const term = normalise(query);
    if (!term || !items.length) return 0;
    const exact = items.findIndex(item => normalise(item.title) === term);
    if (exact >= 0) return exact;
    const prefix = items.findIndex(item => normalise(item.title).startsWith(term));
    return Math.max(0, prefix);
}

export function QuickActions({ sessions, sessionId, workspace, openRequest = 0, onSwitchSession, onPrefill, onRefreshSessions }) {
    const [open, setOpen] = useState(false);
    const [query, setQuery] = useState('');
    const [highlight, setHighlight] = useState(0);
    const [commands, setCommands] = useState([]);
    const [error, setError] = useState('');
    const [commandError, setCommandError] = useState('');
    const [pending, setPending] = useState(false);
    const input = useRef(null);
    const panel = useRef(null);
    const previousFocus = useRef(null);
    const lastOpenRequest = useRef(openRequest);
    const previousSession = useRef(sessionId);
    const generation = useRef(0);
    const busy = useRef(false);
    const items = useMemo(() => quickActionItems({ sessions, commands, workspace, query }), [sessions, commands, workspace, query]);

    const show = (text = '') => {
        previousFocus.current = document.activeElement;
        setQuery(text); setHighlight(0); setError(''); setOpen(true);
    };
    const close = (restore = true) => {
        generation.current++;
        setOpen(false); setQuery(''); setPending(false); busy.current = false;
        if (restore) requestAnimationFrame(() => previousFocus.current?.isConnected && previousFocus.current.focus?.({ preventScroll: true }));
    };
    const activate = async item => {
        if (!item || busy.current) return;
        const epoch = generation.current;
        busy.current = true; setPending(true); setError('');
        try {
            if (item.kind === 'agent') await onSwitchSession(item.sessionId);
            else if (item.kind === 'workspace') await item.run();
            else onPrefill(item.commandName);
            if (epoch === generation.current) close(false);
        } catch (error) {
            if (epoch === generation.current) setError(error.message || 'Quick action failed');
        } finally {
            if (epoch === generation.current) { busy.current = false; setPending(false); }
        }
    };
    useEffect(() => {
        if (lastOpenRequest.current !== openRequest) { lastOpenRequest.current = openRequest; show(); }
    }, [openRequest]);
    useEffect(() => {
        if (previousSession.current !== sessionId) { previousSession.current = sessionId; close(false); }
    }, [sessionId]);
    useEffect(() => {
        let disposed = false;
        setCommands([]); setCommandError('');
        getAgentCommands(sessionId).then(result => {
            if (!disposed) setCommands(Array.isArray(result.commands) ? result.commands : []);
        }).catch(() => { if (!disposed) setCommandError('Commands could not be loaded.'); });
        return () => { disposed = true; };
    }, [sessionId]);
    useLayoutEffect(() => {
        if (open) input.current?.focus();
    }, [open]);
    useEffect(() => {
        if (!open) return;
        // Refresh the same session registry used by the session picker.
        Promise.resolve(onRefreshSessions?.()).catch(() => setError('Sessions could not be refreshed.')); 
    }, [open]);
    useEffect(() => { setHighlight(preferredIndex(items, query)); }, [items, query]);
    useEffect(() => {
        if (open) panel.current?.querySelector(`[data-action-index="${highlight}"]`)?.scrollIntoView({ block: 'nearest' });
    }, [highlight, open]);
    useLayoutEffect(() => {
        const keydown = event => {
            if (!open) {
                if (document.querySelector('dialog[open], [aria-modal="true"], .rename-branch-overlay, .agent-request-modal, .attachment-preview-modal, [data-testid="session-popup"], .compose-model-popup')) return;
                if (!shouldOpenQuickActions(event)) return;
                event.preventDefault(); show(event.key); return;
            }
            if (event.isComposing) return;
            if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); return; }
            if (event.key === 'Tab') {
                const focusable = [...panel.current.querySelectorAll('input, button:not(:disabled)')];
                const index = focusable.indexOf(document.activeElement);
                if (event.shiftKey && index <= 0) { event.preventDefault(); focusable.at(-1)?.focus(); }
                else if (!event.shiftKey && index === focusable.length - 1) { event.preventDefault(); focusable[0]?.focus(); }
                return;
            }
            if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) {
                if (event.key === 'Enter') event.preventDefault();
                return;
            }
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                if (items.length) setHighlight(value => (value + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length);
            } else if (event.key === 'Enter') {
                // Buttons retain native Enter activation after Tab navigation.
                if (document.activeElement?.tagName === 'BUTTON') return;
                event.preventDefault(); void activate(items[highlight]);
            }
        };
        const outside = event => { if (open && !panel.current?.contains(event.target)) close(false); };
        window.addEventListener('keydown', keydown, true);
        document.addEventListener('pointerdown', outside, true);
        return () => {
            window.removeEventListener('keydown', keydown, true);
            document.removeEventListener('pointerdown', outside, true);
        };
    }, [open, items, highlight, pending, onSwitchSession, onPrefill]);
    useEffect(() => () => { generation.current++; }, []);
    if (!open) return null;
    let lastKind = null;
    const labels = { agent: 'Sessions', workspace: 'Workspace', slash: 'Slash commands' };
    return html`
        <div class="timeline-quick-actions-portal">
            <div class="timeline-quick-actions-overlay">
                <div class="timeline-quick-actions" ref=${panel} role="dialog" aria-modal="true" aria-label="Quick actions" aria-busy=${pending}>
                    <div class="timeline-quick-actions-header">
                        <div class="timeline-quick-actions-search-row">
                            <input ref=${input} class="timeline-quick-actions-input" type="text" role="combobox" aria-label="Search quick actions" aria-autocomplete="list" aria-expanded="true" aria-controls="quick-actions-list" aria-activedescendant=${items[highlight] ? `quick-action-${highlight}` : undefined} value=${query} placeholder="Search sessions, workspace actions and commands…" onInput=${event => setQuery(event.currentTarget.value)} />
                            <div class="timeline-quick-actions-hints" aria-hidden="true">
                                <span class="timeline-quick-actions-keyhint"><kbd>↑↓</kbd>Move</span>
                                <span class="timeline-quick-actions-keyhint"><kbd>↵</kbd>Select</span>
                                <span class="timeline-quick-actions-keyhint"><kbd>Esc</kbd>Close</span>
                            </div>
                            <button type="button" class="icon-btn" aria-label="Close quick actions" onClick=${() => close()}>×</button>
                        </div>
                    </div>
                    ${(error || commandError) && html`<div class="timeline-quick-actions-empty" role="alert">${error || commandError}</div>`}
                    <div class="timeline-quick-actions-list" id="quick-actions-list" role="listbox" aria-label="Quick actions results">
                        ${!items.length && html`<div class="timeline-quick-actions-empty" role="status">No quick actions match.</div>`}
                        ${items.map((item, index) => {
                            const section = lastKind !== item.kind; lastKind = item.kind;
                            return html`
                                ${section && html`<div class="timeline-quick-actions-section" role="presentation">${labels[item.kind]}</div>`}
                                <button key=${item.key} type="button" role="option" aria-selected=${highlight === index} id=${`quick-action-${index}`} data-action-index=${index} data-action-key=${item.key} class=${`timeline-quick-actions-item timeline-quick-actions-item-${item.kind}${highlight === index ? ' active' : ''}`} disabled=${pending} onClick=${() => activate(item)}>
                                    <span class="timeline-quick-actions-item-media"><span class="timeline-quick-actions-item-placeholder" aria-hidden="true">${item.visual}</span></span>
                                    <span class="timeline-quick-actions-item-copy"><span class="timeline-quick-actions-item-title-row"><span class="timeline-quick-actions-item-title">${item.title}</span><span class="timeline-quick-actions-item-action-hint">${item.hint}</span></span><span class="timeline-quick-actions-item-subtitle">${item.subtitle}</span></span>
                                    <span class="timeline-quick-actions-item-category">${labels[item.kind]}</span>
                                </button>`;
                        })}
                    </div>
                </div>
            </div>
        </div>`;
}
