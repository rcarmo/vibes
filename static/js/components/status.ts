import { html, useEffect, useState } from '../vendor/preact-htm.js';
import { addToWhitelist, respondToAgentRequest } from '../api.ts';
import { describeRateLimit } from '../features/agent/status-utils.ts';

type PanelKey = 'plan' | 'thought' | 'draft';

interface PreviewPayload {
    text?: string;
    fullText?: string;
    full_text?: string;
    totalLines?: number;
}

interface NormalizedPreview {
    text: string;
    totalLines: number;
    fullText: string;
}

interface TruncatedPreview {
    text: string;
    omitted: number;
    totalLines: number;
    visibleLines?: number;
}

interface AgentStatusPayload {
    type?: string;
    title?: string;
    status?: string;
    last_activity?: boolean;
    lastActivity?: boolean;
    turn_id?: string;
}

interface ToolCallPayload {
    title?: string;
    description?: string;
    rawInput?: {
        command?: string;
        commands?: string[];
        diff?: string;
        fileName?: string;
        path?: string;
        description?: string;
        explanation?: string;
    };
    locations?: Array<{ path?: string }>;
}

interface AgentRequestOption {
    optionId?: string;
    id?: string;
    kind?: string;
    name?: string;
    label?: string;
}

interface PendingAgentRequest {
    request_id: string;
    tool_call?: ToolCallPayload;
    options?: AgentRequestOption[];
}

interface AgentStatusProps {
    status?: AgentStatusPayload | null;
    draft?: string | PreviewPayload | null;
    plan?: string | PreviewPayload | null;
    thought?: string | PreviewPayload | null;
    pendingRequest?: PendingAgentRequest | null;
    turnId?: string | null;
    steerQueued?: boolean;
    renderThinkingMarkdown?: (value: string) => string;
    getTurnColor?: (turnId?: string | null) => string | null;
    onExpandPanel?: (panel: 'draft' | 'thought', turnId?: string | null) => Promise<unknown> | unknown;
    onPanelExpandedChange?: (panel: 'draft' | 'thought', expanded: boolean, turnId?: string | null) => void;
}

interface ThinkingPanelArgs {
    panelTitle: string;
    text: string;
    totalLines: number;
    maxLines?: number;
    titleClass?: string;
    panelKey: PanelKey;
}

interface AgentRequestModalProps {
    request?: PendingAgentRequest | null;
    onRespond?: () => void;
}

interface ConnectionStatusProps {
    status?: string;
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
}: AgentStatusProps) {
    const THOUGHT_MAX_LINES = 8;
    const DRAFT_MAX_LINES = 8;
    const PREVIEW_MAX_CHARS_PER_LINE = 160;

    const normalizePreview = (value: string | PreviewPayload | null | undefined): NormalizedPreview => {
        if (!value) return { text: '', totalLines: 0, fullText: '' };
        if (typeof value === 'string') {
            const totalLines = value ? value.replace(/\r\n/g, '\n').split('\n').length : 0;
            return { text: value, totalLines, fullText: value };
        }
        const text = value.text || '';
        const fullText = value.fullText || value.full_text || text;
        const totalLines = Number.isFinite(value.totalLines)
            ? Number(value.totalLines)
            : (fullText ? fullText.replace(/\r\n/g, '\n').split('\n').length : 0);
        return { text, totalLines, fullText };
    };

    const countSoftLines = (line: string): number => {
        if (!line) return 1;
        return Math.max(1, Math.ceil(line.length / PREVIEW_MAX_CHARS_PER_LINE));
    };

    const truncateLines = (text: string, maxLines: number, totalLinesOverride?: number): TruncatedPreview => {
        const value = (text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
        if (!value) {
            const totalLines = Number.isFinite(totalLinesOverride) ? Number(totalLinesOverride) : 0;
            return { text: '', omitted: 0, totalLines, visibleLines: 0 };
        }
        const lines = value.split('\n');
        const clipped = lines.length > maxLines ? lines.slice(0, maxLines).join('\n') : value;
        const totalLines = Number.isFinite(totalLinesOverride) ? Number(totalLinesOverride) : lines.reduce((acc: number, line: string) => acc + countSoftLines(line), 0);
        const visibleLines = clipped
            ? clipped.split('\n').reduce((acc: number, line: string) => acc + countSoftLines(line), 0)
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

    const [expandedPanels, setExpandedPanels] = useState(new Set() as Set<PanelKey>);
    const toggleExpand = (key: PanelKey) => {
        setExpandedPanels((prev: Set<PanelKey>) => {
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
    const renderThinking = renderThinkingMarkdown || ((value: string) => value || '');

    const renderThinkingPanel = ({ panelTitle, text, totalLines, maxLines, titleClass, panelKey }: ThinkingPanelArgs) => {
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
        const truncated = typeof effectiveMax === 'number'
            ? truncateLines(sourceText, effectiveMax, totalLines)
            : { text: sourceText || '', omitted: 0, totalLines: Number.isFinite(totalLines) ? totalLines : 0 };
        if (!truncated.text && !(Number.isFinite(truncated.totalLines) && truncated.totalLines > 0)) return null;
        const bodyClass = `agent-thinking-body${isCollapsible ? ' agent-thinking-body-collapsible' : ''}`;
        const bodyStyle = isCollapsible ? `--agent-thinking-collapsed-lines: ${maxLines};` : '';
        return html`
            <div
                class="agent-thinking"
                data-expanded=${isExpanded ? 'true' : 'false'}
                data-collapsible=${isCollapsible ? 'true' : 'false'}
                style=${turnColor ? `--turn-color: ${turnColor};` : ''}
            >
                <div class="agent-thinking-title ${titleClass || ''}">
                    ${turnColor && html`<span class=${dotClass} aria-hidden="true"></span>`}
                    ${panelTitle}
                </div>
                <div
                    class=${bodyClass}
                    style=${bodyStyle}
                    dangerouslySetInnerHTML=${{ __html: renderThinking(truncated.text) }}
                />
                ${!isExpanded && truncated.omitted > 0 && html`
                    <button class="agent-thinking-truncation" onClick=${handleExpand}>
                        ▸ ${truncated.omitted} more lines
                    </button>
                `}
                ${isExpanded && truncated.omitted === 0 && html`
                    <button class="agent-thinking-truncation" onClick=${handleExpand}>
                        ▴ show less
                    </button>
                `}
            </div>
        `;
    };

    const pendingTitle = pendingRequest?.tool_call?.title;
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
            ${hasThought && renderThinkingPanel({
                panelTitle: 'Thoughts',
                text: thoughtInfo.text,
                totalLines: thoughtInfo.totalLines,
                maxLines: THOUGHT_MAX_LINES,
                titleClass: 'thought',
                panelKey: 'thought',
            })}
            ${hasDraft && renderThinkingPanel({
                panelTitle: 'Draft',
                text: draftInfo.text,
                totalLines: draftInfo.totalLines,
                maxLines: DRAFT_MAX_LINES,
                titleClass: 'thought',
                panelKey: 'draft',
            })}
            ${status && html`
                <div class=${`agent-status${isLastActivity ? ' agent-status-last-activity' : ''}${status?.type === 'error' ? ' agent-status-error' : ''}`} style=${turnColor ? `--turn-color: ${turnColor};` : ''}>
                    ${turnColor && html`<span class=${dotClass} aria-hidden="true"></span>`}
                    ${status?.type === 'error' ? html`<span class="agent-status-error-icon" aria-hidden="true">⚠</span>` : (!isLastActivity && html`<div class="agent-status-spinner"></div>`)}
                    <span class="agent-status-text">${content}</span>
                </div>
            `}
        </div>
    `;
}

export function AgentRequestModal({ request, onRespond }: AgentRequestModalProps) {
    if (!request) return null;

    const { request_id, tool_call, options } = request;
    const title = tool_call?.title || 'Agent Request';

    const rawInput = tool_call?.rawInput || {};
    const command = rawInput.command || (rawInput.commands && rawInput.commands[0]) || null;
    const diff = rawInput.diff || null;
    const fileName = rawInput.fileName || rawInput.path || null;
    const explanation = tool_call?.description || rawInput.description || rawInput.explanation || null;
    const locations = Array.isArray(tool_call?.locations) ? tool_call.locations : [];
    const locationPaths = locations
        .map((loc: { path?: string }) => loc?.path)
        .filter((path): path is string => Boolean(path));
    const uniquePaths = Array.from(new Set([fileName, ...locationPaths].filter(Boolean)));

    const handleResponse = async (outcome: string) => {
        try {
            await respondToAgentRequest(request_id, outcome);
            onRespond?.();
        } catch (e) {
            console.error('Failed to respond to agent request:', e);
        }
    };

    const handleAlwaysAllow = async () => {
        try {
            await addToWhitelist(title, `Auto-approved: ${title}`);
            await respondToAgentRequest(request_id, 'approved');
            onRespond?.();
        } catch (e) {
            console.error('Failed to add to whitelist:', e);
        }
    };

    const hasOptions = options && options.length > 0;

    return html`
        <div class="agent-request-modal">
            <div class="agent-request-content">
                <div class="agent-request-header">
                    <div class="agent-request-icon">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                        </svg>
                    </div>
                    <div class="agent-request-title">${title}</div>
                </div>
                ${(explanation || command || diff || uniquePaths.length > 0) && html`
                    <div class="agent-request-body">
                        ${explanation && html`
                            <div class="agent-request-description">${explanation}</div>
                        `}
                        ${uniquePaths.length > 0 && html`
                            <div class="agent-request-files">
                                <div class="agent-request-subtitle">Files</div>
                                <ul>
                                    ${uniquePaths.map((path, idx) => html`<li key=${idx}>${path}</li>`)}
                                </ul>
                            </div>
                        `}
                        ${command && html`
                            <pre class="agent-request-command">${command}</pre>
                        `}
                        ${diff && html`
                            <details class="agent-request-diff">
                                <summary>Proposed diff</summary>
                                <pre>${diff}</pre>
                            </details>
                        `}
                    </div>
                `}
                <div class="agent-request-actions">
                    ${hasOptions ? (
                        options.map((opt: AgentRequestOption) => html`
                            <button
                                key=${opt.optionId || opt.id || String(opt)}
                                class="agent-request-btn ${opt.kind === 'allow_once' || opt.kind === 'allow_always' ? 'primary' : ''}"
                                onClick=${() => handleResponse(opt.optionId || opt.id || String(opt))}
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
            </div>
        </div>
    `;
}

export function ConnectionStatus({ status }: ConnectionStatusProps) {
    if (status === 'connected') return null;

    return html`
        <div class="connection-status ${status}">
            ${status === 'disconnected' ? 'Reconnecting...' : status}
        </div>
    `;
}
