import { html, useEffect, useRef, useState } from '../vendor/preact-htm.js';
import { addToWhitelist, respondToAgentRequest } from '../api.js';
import { disclosureTriangle } from './disclosure-triangle.js';
import { agentRequestDetails } from './agent-request-details.js';
import { copyPermissionText } from './permission-clipboard.js';

const RATE_LIMIT_RE = /429|rate.?limit|too many requests|requests per minute|tokens per minute|rpm|tpm/i;

function describeRateLimit(text) {
    if (!text || !RATE_LIMIT_RE.test(text)) return null;
    if (/tokens?\s*per\s*minute|tpm/i.test(text)) return '⚠ Rate limited (TPM — tokens per minute)';
    if (/requests?\s*per\s*minute|rpm/i.test(text)) return '⚠ Rate limited (RPM — requests per minute)';
    return '⚠ Rate limited';
}

export function AgentStatus({
    status,
    draft,
    plan,
    thought,
    pendingRequest,
    turnId,
    steerQueued,
    renderThinkingMarkdown,
    getTurnColor,
    onExpandPanel,
    onPanelExpandedChange,
}) {
    const THOUGHT_MAX_LINES = 9;
    const DRAFT_MAX_LINES = 9;
    const PREVIEW_MAX_CHARS_PER_LINE = 160;

    const normalizePreview = (value) => {
        if (!value) return { text: '', totalLines: 0, fullText: '' };
        if (typeof value === 'string') {
            const totalLines = value ? value.replace(/\r\n/g, '\n').split('\n').length : 0;
            return { text: value, totalLines, fullText: value };
        }
        const text = value.text || '';
        const fullText = value.fullText || value.full_text || text;
        const totalLines = Number.isFinite(value.totalLines)
            ? value.totalLines
            : (fullText ? fullText.replace(/\r\n/g, '\n').split('\n').length : 0);
        return { text, totalLines, fullText };
    };

    const countSoftLines = (line) => {
        if (!line) return 1;
        return Math.max(1, Math.ceil(line.length / PREVIEW_MAX_CHARS_PER_LINE));
    };

    const truncateLines = (text, maxLines, totalLinesOverride, direction = 'head') => {
        const value = (text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
        if (!value) {
            const totalLines = Number.isFinite(totalLinesOverride) ? totalLinesOverride : 0;
            return { text: '', omitted: 0, totalLines, visibleLines: 0 };
        }
        const lines = value.split('\n');
        const clipped = lines.length > maxLines
            ? (direction === 'tail' ? lines.slice(-maxLines) : lines.slice(0, maxLines)).join('\n')
            : value;
        const totalLines = Number.isFinite(totalLinesOverride) ? totalLinesOverride : lines.reduce((acc, line) => acc + countSoftLines(line), 0);
        const visibleLines = clipped
            ? clipped.split('\n').reduce((acc, line) => acc + countSoftLines(line), 0)
            : 0;
        const omitted = Math.max(totalLines - visibleLines, 0);
        return { text: clipped, omitted, totalLines, visibleLines };
    };

    const planInfo = normalizePreview(plan);
    const thoughtInfo = normalizePreview(thought);
    const draftInfo = normalizePreview(draft);
    const hasPlan = Boolean(planInfo.text) || planInfo.totalLines > 0;
    const hasThought = Boolean(thoughtInfo.text) || thoughtInfo.totalLines > 0;
    const hasDraft = Boolean(draftInfo.text) || draftInfo.totalLines > 0;

    const [toolClock, setToolClock] = useState(Date.now());
    useEffect(() => {
        if (!status?.started_at || ['completed', 'failed', 'ended'].includes(status?.status)) return;
        const timer = setInterval(() => setToolClock(Date.now()), 1000);
        return () => clearInterval(timer);
    }, [status?.tool_call_id, status?.started_at, status?.status]);
    const [expandedPanels, setExpandedPanels] = useState(new Set());
    const panelBodies = useRef(new Map());
    const [overflowingPanels, setOverflowingPanels] = useState({});
    useEffect(() => {
        const measure = () => {
            const next = {};
            for (const [key, body] of panelBodies.current) {
                const lineHeight = parseFloat(getComputedStyle(body).lineHeight) || 18;
                next[key] = body.scrollHeight > lineHeight * 9 + 1;
            }
            setOverflowingPanels(previous => JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
        };
        let frame = 0;
        const scheduleMeasure = () => {
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(measure);
        };
        const observer = new ResizeObserver(scheduleMeasure);
        for (const body of panelBodies.current.values()) observer.observe(body);
        scheduleMeasure();
        return () => { cancelAnimationFrame(frame); observer.disconnect(); };
    }, [draftInfo.text, thoughtInfo.text, expandedPanels, turnId]);
    const toggleExpand = (key) => {
        setExpandedPanels((prev) => {
            const next = new Set(prev);
            if (next.has(key)) next.delete(key);
            else next.add(key);
            return next;
        });
    };
    useEffect(() => {
        setExpandedPanels(new Set());
        if (onPanelExpandedChange) {
            onPanelExpandedChange('draft', false, turnId);
            onPanelExpandedChange('thought', false, turnId);
        }
    }, [turnId, onPanelExpandedChange]);

    useEffect(() => {
        for (const [key, body] of panelBodies.current.entries()) {
            if ((key === 'draft' || key === 'thought') && !expandedPanels.has(key)) {
                body.scrollTop = Math.max(0, body.scrollHeight - body.clientHeight);
            }
        }
    }, [draftInfo.text, draftInfo.fullText, thoughtInfo.text, thoughtInfo.fullText, expandedPanels]);

    if (!status && !hasDraft && !hasPlan && !hasThought && !pendingRequest) return null;

    let content = '';
    const title = status?.title;
    const statusText = status?.status;
    const isLastActivity = Boolean(status?.last_activity || status?.lastActivity);
    if (status?.type === 'plan') {
        content = title ? `Planning: ${title}` : 'Planning...';
    } else if (status?.type === 'tool_call') {
        content = title ? `Running: ${title}` : 'Running tool...';
    } else if (status?.type === 'tool_status') {
        content = title ? `${title}: ${statusText || 'Working...'}` : (statusText || 'Working...');
    } else if (status?.type === 'error') {
        const rateMsg = describeRateLimit(title || statusText || '');
        content = rateMsg || title || 'Agent error';
    } else {
        content = title || statusText || 'Working...';
    }
    if (isLastActivity) {
        content = 'Last activity just now';
    }

    const activeTurn = status?.turn_id || turnId;
    const turnColor = getTurnColor ? getTurnColor(activeTurn) : null;
    const dotClass = steerQueued ? 'turn-dot turn-dot-queued' : 'turn-dot';
    const statusIndicator = isLastActivity || status?.type === 'error' ? 'none'
        : status?.tool_name || status?.command || ['tool_call', 'tool_status', 'thinking', 'waiting'].includes(status?.type) ? 'spinner' : 'dot';
    const renderThinking = renderThinkingMarkdown || ((value) => value || '');

    const renderThinkingPanel = ({ panelTitle, text, totalLines, maxLines, titleClass, panelKey }) => {
        const isExpanded = expandedPanels.has(panelKey);
        const handleExpand = async () => {
            if (!isExpanded && onExpandPanel && (panelKey === 'draft' || panelKey === 'thought')) {
                await onExpandPanel(panelKey, activeTurn);
            }
            if (onPanelExpandedChange && (panelKey === 'draft' || panelKey === 'thought')) {
                onPanelExpandedChange(panelKey, !isExpanded, activeTurn);
            }
            toggleExpand(panelKey);
        };
        const isCollapsible = typeof maxLines === 'number';
        const effectiveMax = (isCollapsible && !isExpanded) ? maxLines : undefined;
        // Use fullText for the corresponding info when available
        const info = panelKey === 'plan' ? planInfo : panelKey === 'thought' ? thoughtInfo : draftInfo;
        const sourceText = isExpanded ? (info.fullText || text) : text;
        const cleanedText = (panelKey === 'draft' || panelKey === 'thought')
            ? String(sourceText || '').replace(/<\/?internal>/gi, '').replace(/[\s\u00a0]+$/u, '')
            : sourceText;
        const truncated = typeof effectiveMax === 'number'
            ? truncateLines(cleanedText, effectiveMax, totalLines, (panelKey === 'draft' || panelKey === 'thought') ? 'tail' : 'head')
            : { text: cleanedText || '', omitted: 0, totalLines: Number.isFinite(totalLines) ? totalLines : 0 };
        if (!truncated.text && !(Number.isFinite(truncated.totalLines) && truncated.totalLines > 0)) return null;
        const bodyClass = `agent-thinking-body${isCollapsible ? ' agent-thinking-body-collapsible' : ''}`;
        const bodyStyle = isCollapsible ? `--agent-thinking-collapsed-lines: ${maxLines};` : '';
        return html`
            <div
                class="agent-thinking"
                data-expanded=${isExpanded ? 'true' : 'false'}
                data-collapsible=${isCollapsible ? 'true' : 'false'}
                data-panel-key=${panelKey}
                style=${turnColor ? `--turn-color: ${turnColor};` : ''}
            >
                <div class="agent-thinking-title ${titleClass || ''}">
                    ${turnColor && html`<span class=${dotClass} aria-hidden="true"></span>`}
                    ${panelTitle}
                    ${isCollapsible && (totalLines > maxLines || truncated.omitted > 0 || overflowingPanels[panelKey]) && html`
                        <button class="agent-thinking-truncation" onClick=${handleExpand} title=${isExpanded ? `Show fewer ${panelTitle} lines` : `Show more ${panelTitle}`}>
                            <span class="agent-thinking-truncation-arrow" aria-hidden="true">${disclosureTriangle(isExpanded ? 'up' : 'down')}</span>
                            <span>${isExpanded ? 'less' : 'more…'}</span>
                        </button>
                    `}
                </div>
                <div
                    class=${bodyClass}
                    style=${bodyStyle}
                    ref=${body => { if (body) panelBodies.current.set(panelKey, body); else panelBodies.current.delete(panelKey); }}
                    dangerouslySetInnerHTML=${{ __html: renderThinking(truncated.text) }}
                />
            </div>
        `;
    };

    const pendingTitle = pendingRequest ? agentRequestDetails(pendingRequest).title : null;
    const pendingMessage = pendingTitle ? `Awaiting approval: ${pendingTitle}` : 'Awaiting approval';

    return html`
        <div class="agent-status-panel">
            ${pendingRequest && html`
                <div class="agent-status agent-status-request" aria-live="polite" style=${turnColor ? `--turn-color: ${turnColor};` : ''}>
                    <span class=${dotClass} aria-hidden="true"></span>
                    <div class="agent-status-spinner"></div>
                    <span class="agent-status-text">${pendingMessage}</span>
                </div>
            `}
            ${hasPlan && renderThinkingPanel({
                panelTitle: 'Planning',
                text: planInfo.text,
                totalLines: planInfo.totalLines,
                panelKey: 'plan',
            })}
            ${hasDraft && renderThinkingPanel({
                panelTitle: 'Draft',
                text: draftInfo.text,
                totalLines: draftInfo.totalLines,
                maxLines: DRAFT_MAX_LINES,
                titleClass: 'thought',
                panelKey: 'draft',
            })}
            ${hasThought && renderThinkingPanel({
                panelTitle: 'Thoughts',
                text: thoughtInfo.text,
                totalLines: thoughtInfo.totalLines,
                maxLines: THOUGHT_MAX_LINES,
                titleClass: 'thought',
                panelKey: 'thought',
            })}
            ${status?.output && html`<div class="thinking-panel">
                <button type="button" class="thinking-panel-header" aria-expanded=${expandedPanels.has('output')} onClick=${() => toggleThinking('output')}>Output${status.output_truncated ? ' (truncated)' : ''}${status.started_at ? ` · ${Math.max(0, Math.floor(((status.ended_at ? status.ended_at * 1000 : toolClock) - status.started_at * 1000) / 1000))}s` : ''}</button>
                <pre class="thinking-panel-body" style=${expandedPanels.has('output') ? '' : 'max-height:9em;overflow:auto'}>${status.output}</pre>
            </div>`}
            ${status && html`
                <div class=${`agent-status${isLastActivity ? ' agent-status-last-activity' : ''}${status?.type === 'error' ? ' agent-status-error' : ''}`} style=${turnColor ? `--turn-color: ${turnColor};` : ''}>
                    ${turnColor && statusIndicator === 'dot' && html`<span class=${dotClass} aria-hidden="true"></span>`}
                    ${status?.type === 'error' ? html`<span class="agent-status-error-icon" aria-hidden="true">⚠</span>` : (statusIndicator === 'spinner' && html`<div class="agent-status-spinner"></div>`)}
                    <span class="agent-status-text">${content}</span>
                </div>
            `}
        </div>
    `;
}

export function AgentRequestModal({ request, onRespond }) {
    const [answer, setAnswer] = useState('');
    const [responseError, setResponseError] = useState('');
    const [copyState, setCopyState] = useState('');
    const dialogRef = useRef(null);
    const currentRequest = useRef(request?.request_id);
    currentRequest.current = request?.request_id;
    useEffect(() => {
        setAnswer(''); setResponseError(''); setCopyState('');
        const dialog = dialogRef.current;
        if (!dialog || !request) return;
        const previous = document.activeElement;
        // Focus the dialog, never an approval button: Enter must not approve by default.
        dialog.focus({ preventScroll: true });
        return () => { if (previous?.isConnected && dialog.contains(document.activeElement)) previous.focus?.({ preventScroll: true }); };
    }, [request?.request_id]);
    if (!request) return null;

    const { request_id, options } = request;
    const { title, command, diff, explanation, paths: uniquePaths, fields, warnings, technical } = agentRequestDetails(request);

    const handleResponse = async (outcome) => {
        try {
            await respondToAgentRequest(request_id, outcome, outcome === 'freeform' ? answer : undefined);
            onRespond(request_id);
        } catch (e) {
            console.error('Failed to respond to agent request:', e);
            setResponseError(String(e.message || e));
        }
    };

    const handleAlwaysAllow = async () => {
        try {
            await addToWhitelist(title, `Auto-approved: ${title}`);
            await respondToAgentRequest(request_id, 'approved');
            onRespond(request_id);
        } catch (e) {
            console.error('Failed to add to whitelist:', e);
        }
    };

    const hasOptions = options && options.length > 0;
    const permission = Boolean(technical);
    const orderedOptions = permission && hasOptions
        ? [...options].sort((a, b) => Number(a.kind !== 'reject_once') - Number(b.kind !== 'reject_once'))
        : options;
    const copyCommand = async () => {
        try {
            const ok = await copyPermissionText(command, dialogRef.current);
            if (currentRequest.current === request_id) setCopyState(ok ? 'Copied' : 'Copy unavailable — select text');
        } catch { if (currentRequest.current === request_id) setCopyState('Copy unavailable — select text'); }
    };
    const trapFocus = (event) => {
        if (event.key !== 'Tab') return;
        const controls = [...dialogRef.current.querySelectorAll('button:not(:disabled), summary, textarea, a[href], [tabindex="0"]')].filter(el => el.getClientRects().length);
        if (!controls.length) { event.preventDefault(); return; }
        const first = controls[0], last = controls.at(-1), active = document.activeElement;
        if (event.shiftKey && (active === first || active === dialogRef.current)) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && (active === last || active === dialogRef.current)) { event.preventDefault(); first.focus(); }
    };

    return html`
        <div class="agent-request-modal permission-review" onKeyDown=${trapFocus}>
            <div class="agent-request-content" ref=${dialogRef} role="dialog" aria-modal="true" aria-labelledby="agent-request-heading" tabindex="-1">
                <div class="agent-request-header">
                    <div class="agent-request-icon">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                        </svg>
                    </div>
                    <div class="agent-request-heading-group">
                        <div class="agent-request-eyebrow">${permission ? 'Permission request' : 'Agent question'}</div>
                        <h2 id="agent-request-heading" class="agent-request-title">${title}</h2>
                    </div>
                </div>
                <div class="agent-request-body" tabindex="0" aria-label="Request details">
                        ${explanation && html`
                            <div class="agent-request-description">${explanation}</div>
                        `}
                        ${warnings.map(warning => html`<div class="agent-request-warning">${warning}</div>`)}
                        ${uniquePaths.length > 0 && html`
                            <div class="agent-request-files">
                                <div class="agent-request-subtitle">Files</div>
                                <ul>
                                    ${uniquePaths.map((path, idx) => html`<li key=${idx}>${path}</li>`)}
                                </ul>
                            </div>
                        `}
                        ${command && html`
                            <section class="agent-request-command-section" aria-label="Exact command">
                                <div class="agent-request-section-header">
                                    <span class="agent-request-subtitle">Command</span>
                                    <button type="button" class="agent-request-copy" aria-label="Copy command" onClick=${copyCommand}>Copy</button>
                                </div>
                                <pre class="agent-request-command" data-testid="permission-command">${command}</pre>
                                <div class="agent-request-command-note">Exact command · visual wrapping only${copyState && html`<span role="status">${copyState}</span>`}</div>
                            </section>
                        `}
                        ${fields.map(field => html`<div class="agent-request-files" key=${field.label}>
                            <div class="agent-request-subtitle">${field.label}</div>
                            <pre class="agent-request-command">${field.value}</pre>
                        </div>`)}
                        ${technical && html`<details class="agent-request-diff agent-request-technical">
                            <summary>Technical details</summary>
                            <pre>${technical}</pre>
                        </details>`}
                        ${diff && html`
                            <details class="agent-request-diff">
                                <summary>Proposed diff</summary>
                                <pre>${diff}</pre>
                            </details>
                        `}
                    ${request.allow_freeform && html`
                        <label class="agent-request-answer">Answer<textarea data-testid="agent-freeform-answer" maxlength="8000" value=${answer} onInput=${e => setAnswer(e.target.value)} /></label>
                    `}
                    ${responseError && html`<p class="agent-request-error" role="alert">${responseError}</p>`}
                </div>
                <footer class="agent-request-footer">
                    ${permission && html`<p class="agent-request-scope">Review the full request before allowing it.${options?.some(opt => opt.optionId === 'allow' && opt.kind === 'allow_once') ? ' Allow once applies only to this request.' : ''}</p>`}
                    <div class=${`agent-request-actions${permission ? ' permission-actions' : ''}`}>
                    ${request.allow_freeform && html`<button type="button" class="agent-request-btn primary" disabled=${!answer.trim()} onClick=${() => handleResponse('freeform')}>Submit answer</button>`}
                    ${hasOptions ? (
                        orderedOptions.map((opt) => html`
                            <button
                                key=${opt.optionId || opt.id || String(opt)}
                                type="button"
                                class="agent-request-btn ${opt.kind === 'allow_once' || opt.kind === 'allow_always' ? 'primary' : ''}"
                                onClick=${() => handleResponse(opt.optionId || opt.id || opt)}
                            >
                                ${opt.name || opt.label || opt.optionId || opt.id || String(opt)}
                            </button>
                        `)
                    ) : html`
                        <button class="agent-request-btn primary" onClick=${() => handleResponse('approved')}>
                            Allow
                        </button>
                        <button class="agent-request-btn" onClick=${() => handleResponse('denied')}>
                            Deny
                        </button>
                        <button class="agent-request-btn always-allow" onClick=${handleAlwaysAllow}>
                            Always Allow This
                        </button>
                    `}
                    </div>
                </footer>
            </div>
        </div>
    `;
}

export function ConnectionStatus({ status }) {
    if (status === 'connected') return null;

    return html`
        <div class="connection-status ${status}">
            ${status === 'disconnected' ? 'Reconnecting...' : status}
        </div>
    `;
}
