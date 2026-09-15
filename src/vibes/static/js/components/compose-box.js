import { AgentCapabilities } from './agent-capabilities.js';
import { loadModelPins, saveModelPins, modelPinStorage } from './model-pins.js';
import { createSpeechInput, speechInputConstructor, shouldStartSpeechPushToTalk } from './compose-speech.js';
import { sessionMentionQuery, sessionMentionMatches, insertSessionMention } from './session-mentions.js';
import { composeDrafts } from './compose-drafts.js';
import { usagePresentation } from './usage.js';
import { useComposeSizing } from './compose-sizing.js';
import { loadComposeHistory, saveComposeHistory } from './compose-history.js';
import { FilePill } from './file-pill.js';
import { parseQueuedContent } from './queued-content.js';
import { html, useRef, useState, useEffect, useLayoutEffect, useCallback } from '../vendor/preact-htm.js';
import { abortAgentTurn, getModelPreferences, saveModelPreferences, getSessionModels, changeSessionModel, getSessions, sendAgentMessage, uploadMedia, getAgentCommands } from '../api.js';

/**
 * Slash command definitions for autocomplete.
 * Base set — merged with dynamic commands from the server on connect.
 */
const SLASH_COMMANDS = [
    { name: '/model', description: 'Show or set the model' },
    { name: '/models', description: 'Alias for /model' },
    { name: '/cycle-model', description: 'Cycle to the next available model' },
    { name: '/thinking', description: 'Show or set thinking level' },
    { name: '/cycle-thinking', description: 'Cycle to the next thinking level' },
    { name: '/context', description: 'Show context window usage' },
    { name: '/ctx', description: 'Alias for /context' },
    { name: '/state', description: 'Show current agent/session state' },
    { name: '/prompt', description: 'Show or set the user system prompt' },
    { name: '/theme', description: 'Show or set the UI theme' },
    { name: '/tint', description: 'Set or clear a UI colour tint' },
    { name: '/name', description: 'Show or set the agent display name' },
    { name: '/agent-name', description: 'Show or set the agent display name' },
    { name: '/agent-avatar', description: 'Set or show the agent avatar URL' },
    { name: '/user-name', description: 'Set or show your display name' },
    { name: '/user-avatar', description: 'Set or show your avatar URL' },
    { name: '/user-github', description: 'Set name/avatar from GitHub profile' },
    { name: '/queue', description: 'Queue a message for after the current turn' },
    { name: '/abort', description: 'Cancel the current agent operation' },
    { name: '/restart', description: 'Restart the active agent' },
    { name: '/shell', description: 'Run a shell command' },
    { name: '/bash', description: 'Run a shell command and return output inline' },
    { name: '/commands', description: 'List available commands' },
];

function formatK(n) {
    if (n == null) return '?';
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(0) + 'K';
    return String(n);
}

/**
 * Tiny SVG pie chart showing context window usage.
 * Green when <75%, amber 75–90%, red >90%. Tooltip shows exact numbers.
 */
function ContextPie({ usage, onCompact, disabled, compacting }) {
    const canCompact = usage.compactCommand === '/compact';
    const known = typeof usage.percent === 'number' && Number.isFinite(usage.percent) && usage.percent >= 0;
    if (!known && !canCompact) return null;
    const Tag = 'button';
    const pct = known ? usage.percent : 0;
    const tokens = usage.tokens;
    const ctxWindow = usage.contextWindow;
    const label = !known ? 'Context usage unavailable' : Number.isFinite(tokens) && tokens >= 0 && Number.isFinite(ctxWindow) && ctxWindow > 0
        ? `Context: ${formatK(tokens)} / ${formatK(ctxWindow)} tokens (${pct.toFixed(0)}%)`
        : `Context: ${pct.toFixed(0)}%`;

    const r = 9;
    const circ = 2 * Math.PI * r;
    const filled = (Math.min(100, pct) / 100) * circ;

    const color = pct > 90 ? 'var(--context-red, #ef4444)'
        : pct > 75 ? 'var(--context-amber, #f59e0b)'
            : 'var(--context-green, #22c55e)';

    return html`
        <${Tag} class=${`compose-context-pie${compacting ? ' is-compacting' : ''}`} type="button"
            aria-label=${canCompact ? `${label}. Compact context` : label}
            disabled=${!canCompact || disabled} aria-busy=${compacting ? 'true' : undefined}
            onClick=${canCompact ? onCompact : undefined}
            title=${[label, usagePresentation(usage).title, canCompact && 'Compact context (agent-advertised /compact)'].filter(Boolean).join('\n')}>
            <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
                <circle cx="11" cy="11" r=${r}
                    fill="none"
                    stroke="var(--border-color)"
                    stroke-width="2.5" />
                <circle cx="11" cy="11" r=${r}
                    fill="none"
                    stroke=${color}
                    stroke-width="2.5"
                    stroke-dasharray=${`${filled} ${circ}`}
                    stroke-linecap="round"
                    transform="rotate(-90 11 11)" />
            </svg>
        <//>
    `;
}

export function FollowupQueue({ items, onRemove, onSteer, onReorder }) {
    if (!items || items.length === 0) return null;
    return html`
        <div class="compose-queue-stack" aria-label="Queued follow-ups" role="list">
            ${items.map((item) => {
                const peers = items.filter(other => other.agent_id === item.agent_id && other.thread_id === item.thread_id);
                const position = peers.findIndex(other => other.row_id === item.row_id);
                const parsed = parseQueuedContent(item.content);
                const content = parsed.text;
                const preview = content.length > 140 ? `${content.slice(0, 140)}…` : content;
                const itemLabel = preview || 'Untitled follow-up';
                return html`
                    <div key=${item.row_id} class="compose-queue-stack-item" data-testid="queue-item" role="listitem">
                        <div class="compose-queue-stack-content" title=${content}>
                            <span class="compose-queue-dot" aria-hidden="true"></span>
                            <div class="compose-queue-stack-text">${content ? itemLabel : parsed.refs.length ? '' : itemLabel}</div>
                            ${parsed.refs.length > 0 && html`<div class="compose-queue-stack-refs">${parsed.refs.map((ref, index) => html`<${FilePill} key=${index} prefix="compose" icon=${ref.kind === 'attachment' ? 'file' : ref.kind} label=${ref.label} title=${ref.title} />`)}</div>`}
                        </div>
                        <div class="compose-queue-stack-actions" role="group" aria-label="Queue controls">
                            ${peers.length > 1 && html`<button type="button" data-action="move-up" class="compose-queue-stack-move-btn" disabled=${position === 0} title="Move up" aria-label="Move up in queue" onClick=${() => onReorder?.(item.row_id, 'up')}>
                                <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 10l5-5 5 5" /></svg>
                            </button>
                            <button type="button" data-action="move-down" class="compose-queue-stack-move-btn" disabled=${position === peers.length - 1} title="Move down" aria-label="Move down in queue" onClick=${() => onReorder?.(item.row_id, 'down')}>
                                <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6l5 5 5-5" /></svg>
                            </button>`}
                            <button
                                type="button"
                                class="compose-queue-stack-steer-btn"
                                title="Inject as steer"
                                aria-label=${`Promote queued item to steering: ${itemLabel}`}
                                onClick=${() => onSteer?.(item.row_id)}
                            >
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                    <path d="M4 20H10C12.2091 20 14 18.2091 14 16V4" />
                                    <path d="M8 10L14 4L20 10" />
                                </svg>
                                <span>Steer</span>
                            </button>
                            <button
                                type="button"
                                class="compose-queue-stack-close-btn queue-remove"
                                title="Cancel queued item"
                                aria-label=${`Cancel queued item: ${itemLabel}`}
                                onClick=${() => onRemove?.(item.row_id)}
                            >
                                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                            </button>
                        </div>
                    </div>
                `;
            })}
        </div>
    `;
}

export function ComposeBox({
    sessionId = 'default',
    onPost,
    prefillRequest = null,
    onOpenQuickActions,
    sessionTrigger = null,
    sessionPicker = null,
    queuedFollowups = [],
    onQueueRemove,
    onQueueSteer,
    onQueueReorder,
    onFocus,
    searchMode,
    onSearch,
    onEnterSearch,
    onExitSearch,
    fileRefs = [],
    folderRefs = [],
    onRemoveFolderRef,
    onClearFolderRefs,
    onRemoveFileRef,
    onClearFileRefs,
    messageRefs = [],
    onRemoveMessageRef,
    onClearMessageRefs,
    activeModel = null,
    defaultAgent = null,
    thinkingLevel = null,
    supportsThinking = false,
    isCompacting = false,
    contextUsage = null,
    agentBusy = false,
    activeTurnId = null,
    onModelChange,
    onModelStateChange,
    notificationsEnabled = false,
    notificationPermission = 'default',
    onToggleNotifications,
}) {
    const [content, setContent] = useState(() => composeDrafts.load(sessionId).text);
    const [aborting, setAborting] = useState(false);
    const abortPending = useRef(false);
    const [searchText, setSearchText] = useState('');
    const [speechState, setSpeechState] = useState({ kind: 'idle', detail: '' });
    const speechRef = useRef(null);
    const speechHeld = useRef(false);
    const speechPointer = useRef(null);
    const suppressSpeechClick = useRef(false);
    const speechAvailable = !!speechInputConstructor();
    const speechActive = ['requesting_permission', 'listening'].includes(speechState.kind);
    const cancelSpeech = () => {
        speechRef.current?.dispose(); speechRef.current = null;
        speechHeld.current = false;
        speechPointer.current = null;
        setSpeechState({ kind: 'idle', detail: '' });
    };
    const startSpeech = () => {
        if (!speechAvailable || searchMode || loading || speechRef.current) return;
        const controller = createSpeechInput(speechInputConstructor(), {
            base: content, onText: setContent,
            onState: (kind, detail = '') => {
                setSpeechState({ kind, detail });
                if (kind === 'idle' || kind === 'error') {
                    speechRef.current?.dispose(); speechRef.current = null;
                }
            },
        });
        speechRef.current = controller; controller.start();
    };
    const handleSpeechPointerDown = event => {
        suppressSpeechClick.current = false;
        if (event.pointerType === 'mouse' || event.button !== 0 || !event.isPrimary) return;
        if (!shouldStartSpeechPushToTalk({ key: ' ' }, content, { searchMode, available: speechAvailable && !loading, active: !!speechRef.current })) return;
        event.preventDefault();
        speechPointer.current = event.pointerId;
        suppressSpeechClick.current = true;
        event.currentTarget.setPointerCapture?.(event.pointerId);
        startSpeech();
    };
    const releaseSpeechPointer = event => {
        if (speechPointer.current !== event.pointerId) return;
        speechPointer.current = null;
        if (event.type === 'pointercancel' || event.type === 'lostpointercapture') cancelSpeech();
        else speechRef.current?.stop();
    };
    useEffect(() => {
        cancelSpeech();
        const blur = () => cancelSpeech();
        const visibility = () => { if (document.hidden) cancelSpeech(); };
        const keyup = event => {
            if (speechHeld.current && (event.key === ' ' || event.code === 'Space')) {
                event.preventDefault(); speechHeld.current = false; speechRef.current?.stop();
            }
        };
        window.addEventListener('blur', blur);
        document.addEventListener('visibilitychange', visibility);
        window.addEventListener('keyup', keyup);
        return () => {
            speechRef.current?.dispose(); speechRef.current = null; speechHeld.current = false;
            window.removeEventListener('blur', blur); window.removeEventListener('keyup', keyup);
            document.removeEventListener('visibilitychange', visibility);
        };
    }, [sessionId, searchMode]);
    const [mentionRange, setMentionRange] = useState(null);
    const [mentionSessions, setMentionSessions] = useState([]);
    const [mentionIndex, setMentionIndex] = useState(0);
    const mentioning = !searchMode && mentionRange !== null;
    useEffect(() => {
        setMentionRange(null);
        setMentionSessions([]);
    }, [sessionId, searchMode]);
    useEffect(() => {
        if (!mentioning) { setMentionSessions([]); return; }
        let disposed = false;
        getSessions().then(result => { if (!disposed) setMentionSessions(result.sessions || []); })
            .catch(() => { if (!disposed) setMentionSessions([]); });
        return () => { disposed = true; };
    }, [mentioning, sessionId]);
    const mentionMatches = !searchMode && mentionRange && sessionMentionQuery(content, mentionRange.end)?.start === mentionRange.start ? sessionMentionMatches(mentionSessions, mentionRange.query) : [];
    const acceptMention = item => {
        const caret = mentionRange.start + `@session:${item.id} `.length;
        setContent(insertSessionMention(content, mentionRange, item.id));
        setMentionRange(null);
        requestAnimationFrame(() => { textareaRef.current?.focus(); textareaRef.current?.setSelectionRange(caret, caret); });
    };
    const [searchScope, setSearchScope] = useState('current');
    const [searchFilterImages, setSearchFilterImages] = useState(false);
    const [searchFilterAttachments, setSearchFilterAttachments] = useState(false);
    const [loading, setLoading] = useState(false);
    const [submitError, setSubmitError] = useState('');
    const [uploadProgress, setUploadProgress] = useState(null);
    const uploadController = useRef(null);
    useEffect(() => () => uploadController.current?.abort(), []);
    const [mediaFiles, setMediaFiles] = useState(() => composeDrafts.load(sessionId).files);
    useEffect(() => {
        composeDrafts.save(sessionId, { text: content, files: mediaFiles, fileRefs, folderRefs, messageRefs });
    }, [content, mediaFiles, fileRefs, folderRefs, messageRefs, sessionId]);
    const [isDragActive, setIsDragActive] = useState(false);
    const [slashMatches, setSlashMatches] = useState([]);
    const [slashIndex, setSlashIndex] = useState(0);
    const [showSlash, setShowSlash] = useState(false);
    const [switchingModel, setSwitchingModel] = useState(false);
    const [showModelPopup, setShowModelPopup] = useState(false);
    const [modelOptions, setModelOptions] = useState([]);
    const [sessionCatalog, setSessionCatalog] = useState(null);
    const [loadingModels, setLoadingModels] = useState(false);
    const [modelCatalogError, setModelCatalogError] = useState('');
    const [modelQuery, setModelQuery] = useState('');
    const [highlightedModel, setHighlightedModel] = useState(null);
    const [modelRefresh, setModelRefresh] = useState(0);
    const modelSearchRef = useRef(null);
    const modelMetadata = new Map((sessionCatalog?.models || []).map(model => [`${model.provider}/${model.id}`, model]));
    const modelNames = new Map((sessionCatalog?.models || []).map(model => [`${model.provider}/${model.id}`, model.name || `${model.provider}/${model.id}`]));
    const filteredModels = modelOptions.filter(label => `${label} ${modelNames.get(label) || ''}`.toLowerCase().includes(modelQuery.trim().toLowerCase()));
    const [modelPins, setModelPins] = useState(() => loadModelPins(modelPinStorage()));
    const [modelPinError, setModelPinError] = useState('');
    const [pinSyncStatus, setPinSyncStatus] = useState('');
    const [pinSyncBusy, setPinSyncBusy] = useState(false);
    const pinSyncPending = useRef(false);
    const pinRevision = useRef(0);
    const instancePinEtag = useRef(null);
    const [instancePinsLoaded, setInstancePinsLoaded] = useState(false);
    const syncInstancePins = async save => {
        if (pinSyncPending.current) return;
        const revision = pinRevision.current;
        pinSyncPending.current = true; setPinSyncBusy(true); setPinSyncStatus('');
        try {
            const result = save ? await saveModelPreferences(modelPins, instancePinEtag.current) : await getModelPreferences();
            if (!modelCallbacksActive.current) return;
            instancePinEtag.current = result.etag;
            setInstancePinsLoaded(typeof result.etag === 'string' && result.etag.length > 0);
            if (!save) {
                if (revision !== pinRevision.current) {
                    setPinSyncStatus('Browser pins changed during loading; instance pins were not applied.');
                    return;
                }
                pinRevision.current++;
                setModelPins(result.pins);
                setModelPinError(saveModelPins(modelPinStorage(), result.pins) ? '' : 'Loaded pins are temporary in this browser.');
            }
            if (save) setModelPinError('');
            setPinSyncStatus(save ? 'Pins saved for this instance.' : 'Instance pins loaded into this browser.');
        } catch (error) {
            if (modelCallbacksActive.current) {
                if (error.status === 412) { instancePinEtag.current = null; setInstancePinsLoaded(false); }
                setModelPinError(error.message || 'Pin synchronization failed');
            }
        }
        finally { pinSyncPending.current = false; setPinSyncBusy(false); }
    };
    useEffect(() => {
        const syncPins = event => {
            if (event.key !== null && event.key !== 'vibes_model_pins') return;
            pinRevision.current++;
            setModelPins(loadModelPins(modelPinStorage()));
            setModelPinError('');
        };
        window.addEventListener('storage', syncPins);
        return () => window.removeEventListener('storage', syncPins);
    }, []);
    const toggleModelPin = label => {
        pinRevision.current++;
        const next = modelPins.includes(label) ? modelPins.filter(item => item !== label) : [...modelPins, label].slice(-100);
        setModelPins(next);
        setModelPinError(saveModelPins(modelPinStorage(), next) ? '' : 'Model pins could not be saved in this browser; changes are temporary.');
    };
    const modelGroups = [
        { label: 'Current', models: filteredModels.filter(label => label === activeModel) },
        { label: 'Pinned', models: filteredModels.filter(label => label !== activeModel && modelPins.includes(label)) },
        { label: 'Other models', models: filteredModels.filter(label => label !== activeModel && !modelPins.includes(label)) },
    ].filter(group => group.models.length).map(group => {
        const providers = new Map();
        for (const label of group.models) {
            const provider = label.includes('/') ? label.slice(0, label.indexOf('/')) : 'Unknown provider';
            if (!providers.has(provider)) providers.set(provider, []);
            providers.get(provider).push(label);
        }
        return { ...group, providers: Array.from(providers, ([label, models]) => ({ label, models })) };
    });
    const [slashCommands, setSlashCommands] = useState(sessionId === 'default' ? SLASH_COMMANDS : []);
    const textareaRef = useRef(null);
    // File identity survives failed sends; weak keys release discarded drafts.
    const uploadedFiles = useRef(new WeakMap());
    const slashRef = useRef(null);
    const modelPopupRef = useRef(null);
    const modelSettingsRef = useRef(null);
    const [modelSettingsOpen, setModelSettingsOpen] = useState(false);
    useEffect(() => {
        if (modelSettingsOpen && modelSettingsRef.current && !modelSettingsRef.current.open) modelSettingsRef.current.showModal();
    });
    const modelHintRef = useRef(null);
    const dragCounterRef = useRef(0);
    const historyMax = 200;
    const normaliseHistory = (items) => {
        const seen = new Set();
        const cleaned = [];
        for (const item of items || []) {
            if (typeof item !== 'string') continue;
            const trimmed = item.trim();
            if (!trimmed || seen.has(trimmed)) continue;
            seen.add(trimmed);
            cleaned.push(trimmed);
        }
        return cleaned;
    };
    const loadHistory = () => {
        try { return loadComposeHistory(window.localStorage, sessionId); } catch { return []; }
    };
    const saveHistory = entries => {
        try { saveComposeHistory(window.localStorage, sessionId, entries); } catch { /* Storage unavailable. */ }
    };
    const historyRef = useRef(loadHistory());
    const historyIndexRef = useRef(-1);
    const historyDraftRef = useRef('');
    useEffect(() => {
        historyRef.current = loadHistory();
        historyIndexRef.current = -1;
        historyDraftRef.current = '';
    }, [sessionId]);

    // Fetch commands for this session without consuming another Pi stream.
    useEffect(() => {
        let disposed = false;
        getAgentCommands(sessionId)
            .then((data) => {
                if (!disposed && Array.isArray(data?.commands)) {
                    if (sessionId !== 'default') { setSlashCommands(data.commands); return; }
                    const existing = new Set(SLASH_COMMANDS.map(c => c.name));
                    const merged = [...SLASH_COMMANDS];
                    for (const cmd of data.commands) {
                        if (!existing.has(cmd.name)) {
                            merged.push({ name: cmd.name, description: cmd.description || '' });
                            existing.add(cmd.name);
                        }
                    }
                    setSlashCommands(merged);
                }
            })
            .catch(() => {});
        return () => { disposed = true; };
    }, [sessionId]);

    const canSend = !loading && (content.trim() || mediaFiles.length > 0 || folderRefs.length > 0 || fileRefs.length > 0 || messageRefs.length > 0);
    const canShareLocation = typeof window !== 'undefined'
        && typeof navigator !== 'undefined'
        && Boolean(navigator.geolocation)
        && Boolean(window.isSecureContext);
    const notificationsSupported = typeof window !== 'undefined' && typeof Notification !== 'undefined';
    const notificationsSecure = typeof window !== 'undefined' ? Boolean(window.isSecureContext) : false;
    const notificationDenied = notificationPermission === 'denied';
    const notificationsAvailable = notificationsSupported && notificationsSecure && !notificationDenied;
    const notificationActive = notificationPermission === 'granted' && notificationsEnabled;
    const notificationTitle = notificationActive ? 'Disable notifications' : 'Enable notifications';

    const modelHintLabel = activeModel ? `${activeModel}` : '';
    const thinkingLabel = supportsThinking
        ? `Thinking: ${thinkingLevel || 'default'}`
        : '';

    const modelCallbacksActive = useRef(true);
    useEffect(() => {
        modelCallbacksActive.current = true;
        return () => { modelCallbacksActive.current = false; };
    }, []);
    const emitModelState = (payload) => {
        if (!modelCallbacksActive.current || !payload || typeof payload !== 'object') return;
        const modelLabel = payload.model ?? payload.current;
        if (typeof onModelStateChange === 'function') {
            onModelStateChange({
                model: modelLabel ?? null,
                thinking_level: payload.thinking_level ?? null,
                supports_thinking: payload.supports_thinking,
            });
        }
        if (modelLabel && typeof onModelChange === 'function') {
            onModelChange(modelLabel);
        }
    };

    const { resizeTextarea, handleProps: resizeHandleProps } = useComposeSizing(textareaRef, searchMode ? searchText : content);

    /** Update slash autocomplete matches based on current input. */
    const updateSlashAutocomplete = (value) => {
        if (!value.startsWith('/') || value.includes('\n')) {
            setShowSlash(false);
            setSlashMatches([]);
            return;
        }
        const prefix = value.toLowerCase().split(' ')[0];
        if (prefix.length < 1) {
            setShowSlash(false);
            setSlashMatches([]);
            return;
        }
        const matches = slashCommands.filter((cmd) =>
            cmd.name.startsWith(prefix) || cmd.name.replace(/-/g, '').startsWith(prefix.replace(/-/g, ''))
        );
        if (matches.length > 0 && !(matches.length === 1 && matches[0].name === prefix)) {
            setSlashMatches(matches);
            setSlashIndex(0);
            setShowSlash(true);
        } else {
            setShowSlash(false);
            setSlashMatches([]);
        }
    };

    /** Accept the currently highlighted slash command. */
    const acceptSlashCommand = (cmd) => {
        const current = content;
        const spaceIdx = current.indexOf(' ');
        const args = spaceIdx >= 0 ? current.slice(spaceIdx) : '';
        const newVal = cmd.name + args;
        setContent(newVal);
        setShowSlash(false);
        setSlashMatches([]);
        requestAnimationFrame(() => {
            const textarea = textareaRef.current;
            if (!textarea) return;
            const len = newVal.length;
            textarea.selectionStart = len;
            textarea.selectionEnd = len;
            textarea.focus();
            resizeTextarea();
        });
    };

    const updateValue = (value) => {
        setSubmitError('');
        if (searchMode) {
            setSearchText(value);
        } else {
            setContent(value);
            updateSlashAutocomplete(value);
        }
        requestAnimationFrame(resizeTextarea);
    };

    const appendToValue = (snippet) => {
        const current = searchMode ? searchText : content;
        const prefix = current && !current.endsWith('\n') ? '\n' : '';
        const next = `${current}${prefix}${snippet}`.trimStart();
        updateValue(next);
    };

    const handleCycleModel = async () => {
        if (loadingModels || switchingModel || !sessionCatalog?.available || !modelOptions.length) return;
        const next = modelOptions[(modelOptions.indexOf(activeModel) + 1) % modelOptions.length];
        await handleSelectModel(next);
    };

    const modelMutationPending = useRef(false);
    const handleCycleThinking = async (requestedLevel = null) => {
        if (loading || modelMutationPending.current) return;
        modelMutationPending.current = true;
        setSwitchingModel(true);
        try {
            const catalog = await getSessionModels(sessionId);
            if (!modelCallbacksActive.current) return;
            setSessionCatalog(catalog);
            setModelOptions(catalog.available ? catalog.models.map(item => `${item.provider}/${item.id}`) : []);
            const levels = catalog.available ? catalog.thinking_levels : [];
            if (!levels?.length) throw new Error('Thinking controls unavailable for this session');
            if (requestedLevel !== null && !levels.includes(requestedLevel)) throw new Error('Thinking level is no longer available');
            const next = requestedLevel ?? levels[(levels.indexOf(thinkingLevel) + 1) % levels.length];
            const result = await changeSessionModel(sessionId, { thinking_level: next });
            emitModelState({ model: result.model ? `${result.model.provider}/${result.model.id}` : activeModel,
                thinking_level: result.thinking_level, supports_thinking: result.model?.reasoning === true });
        } catch (error) { setSubmitError(error.message || 'Thinking change failed'); }
        finally { modelMutationPending.current = false; setSwitchingModel(false); }
    };

    const handleSelectModel = async (modelLabel) => {
        if (!modelLabel || loading || modelMutationPending.current) return;
        {
            const model = sessionCatalog?.models?.find(item => `${item.provider}/${item.id}` === modelLabel);
            if (!model) return;
            modelMutationPending.current = true;
            setSwitchingModel(true);
            try {
                const result = await changeSessionModel(sessionId, { provider: model.provider, model_id: model.id });
                emitModelState({ model: result.model ? `${result.model.provider}/${result.model.id}` : activeModel, thinking_level: result.thinking_level, supports_thinking: result.model?.reasoning === true });
                setShowModelPopup(false);
            } catch (error) { setSubmitError(error.message || 'Model change failed'); }
            finally { modelMutationPending.current = false; setSwitchingModel(false); }
            return;
        }
    };

    const modelPickerKeys = event => {
        if (event.isComposing || event.keyCode === 229) return;
        if (event.target === modelSearchRef.current) {
            const choices = Array.from(modelPopupRef.current?.querySelectorAll('[role="option"]:not(:disabled)') || []);
            const index = choices.findIndex(node => node.dataset.modelLabel === highlightedModel);
            if (['ArrowDown', 'ArrowUp'].includes(event.key) && choices.length) {
                event.preventDefault();
                const next = index < 0 ? (event.key === 'ArrowDown' ? 0 : choices.length - 1) : (index + (event.key === 'ArrowDown' ? 1 : -1) + choices.length) % choices.length;
                setHighlightedModel(choices[next].dataset.modelLabel);
                choices[next].scrollIntoView({ block: 'nearest' });
                return;
            }
            if (event.key === 'Enter' && index >= 0) {
                event.preventDefault();
                if (event.altKey) { if (!event.repeat && !event.ctrlKey && !event.metaKey) toggleModelPin(highlightedModel); }
                else void handleSelectModel(highlightedModel);
                return;
            }
        }
        if (event.key === 'Enter' && event.altKey && !event.ctrlKey && !event.metaKey) {
            const choice = event.target?.closest?.('[data-model-label]');
            if (choice) {
                event.preventDefault(); event.stopPropagation();
                if (!event.repeat) {
                    const label = choice.dataset.modelLabel;
                    toggleModelPin(label);
                    requestAnimationFrame(() => {
                        const moved = [...(modelPopupRef.current?.querySelectorAll('[data-model-label]') || [])]
                            .find(item => item.dataset.modelLabel === label);
                        moved?.focus();
                    });
                }
                return;
            }
        }
        if (event.key === 'Escape') {
            event.preventDefault(); event.stopPropagation(); setShowModelPopup(false);
            requestAnimationFrame(() => modelHintRef.current?.focus());
            return;
        }
        if (!['ArrowDown', 'ArrowUp'].includes(event.key) || event.target?.closest?.('select')) return;
        const choices = [...(modelPopupRef.current?.querySelectorAll('[role="option"]:not(:disabled)') || [])];
        if (!choices.length) return;
        event.preventDefault(); event.stopPropagation();
        const current = choices.indexOf(document.activeElement);
        const next = current < 0 ? (event.key === 'ArrowDown' ? 0 : choices.length - 1)
            : (current + (event.key === 'ArrowDown' ? 1 : -1) + choices.length) % choices.length;
        choices[next].focus(); choices[next].scrollIntoView({ block: 'nearest' });
    };
    useLayoutEffect(() => { if (showModelPopup) modelSearchRef.current?.focus(); }, [showModelPopup]);
    useEffect(() => {
        if (!showModelPopup) return;
        setHighlightedModel(previous => filteredModels.includes(previous) ? previous
            : filteredModels.includes(activeModel) ? activeModel : filteredModels[0] || null);
    }, [showModelPopup, modelQuery, modelOptions, activeModel]);
    const toggleModelPopup = (event) => {
        event.preventDefault();
        event.stopPropagation();
        setShowModelPopup((prev) => !prev);
    };

    const usageMeta = usagePresentation(contextUsage);
    const compact = async () => {
        if (loading || agentBusy || isCompacting || contextUsage?.compactCommand !== '/compact') return;
        setLoading(true);
        setSubmitError('');
        try {
            await sendAgentMessage('default', '/compact', null, [], 'auto', sessionId, 'compact');
            onPost?.();
        } catch (error) { setSubmitError(error.message || 'Compaction failed'); }
        finally { setLoading(false); }
    };

    const handleAbort = async () => {
        if (!agentBusy || !activeTurnId || abortPending.current) return;
        abortPending.current = true;
        setAborting(true); setSubmitError('');
        try {
            await abortAgentTurn(sessionId, activeTurnId);
            // Wait for server confirmation; do not clear draft, media or queue.
        } catch (error) {
            setSubmitError(error.message || 'Cancel turn failed');
        } finally {
            abortPending.current = false; setAborting(false);
        }
    };

    const handleSubmit = async (mode = 'auto') => {
        cancelSpeech();
        if (!content.trim() && mediaFiles.length === 0 && fileRefs.length === 0 && folderRefs.length === 0 && messageRefs.length === 0) return;

        setLoading(true);
        setSubmitError('');
        try {
            const mediaIds = [];
            uploadController.current = new AbortController();
            for (const [index, file] of mediaFiles.entries()) {
                if (uploadController.current.signal.aborted) throw new DOMException('Upload cancelled', 'AbortError');
                let id = uploadedFiles.current.get(file);
                if (id === undefined) {
                    const progress = { current: index + 1, total: mediaFiles.length, name: file.name, percent: 0 };
                    setUploadProgress(progress);
                    const result = await uploadMedia(file, {
                        signal: uploadController.current.signal,
                        onProgress: percent => setUploadProgress({ ...progress, percent }),
                    });
                    id = result.id;
                    uploadedFiles.current.set(file, id);
                }
                mediaIds.push(id);
            }

            if (uploadController.current.signal.aborted) throw new DOMException('Upload cancelled', 'AbortError');
            setUploadProgress(null);
            const baseContent = content.trim();
            const fileBlock = fileRefs.length
                ? `Files:\n${fileRefs.map((path) => `- ${path}`).join('\n')}`
                : '';
            const folderBlock = folderRefs.length ? `Folders:\n${folderRefs.map(path => `- ${path}`).join('\n')}` : '';
            const messageBlock = messageRefs.length
                ? `Messages:\n${messageRefs.map((id) => `- ${id}`).join('\n')}`
                : '';
            const mediaBlock = mediaIds.length
                ? `${mediaFiles.every(file => file.type.startsWith('image/')) ? 'Images' : 'Attachments'}:\n${mediaIds.map((id, index) => {
                    const file = mediaFiles[index];
                    const label = file?.name || `image-${index + 1}`;
                    return `- attachment:${id} (${label})`;
                }).join('\n')}`
                : '';
            const message = [baseContent, fileBlock, folderBlock, messageBlock, mediaBlock].filter(Boolean).join('\n\n');

            const response = await sendAgentMessage('default', message, null, mediaIds, mode, sessionId);
            if (response?.command) {
                emitModelState({
                    model: response.command.model_label ?? activeModel ?? null,
                    thinking_level: response.command.thinking_level,
                    supports_thinking: response.command.supports_thinking,
                });
            }

            if (baseContent) {
                const current = historyRef.current;
                const deduped = normaliseHistory(current.filter((item) => item !== baseContent));
                deduped.push(baseContent);
                if (deduped.length > historyMax) {
                    deduped.splice(0, deduped.length - historyMax);
                }
                historyRef.current = deduped;
                saveHistory(deduped);
                historyIndexRef.current = -1;
                historyDraftRef.current = '';
            }

            composeDrafts.clear(sessionId);
            setContent('');
            setMediaFiles([]);
            uploadedFiles.current = new WeakMap();
            onClearFileRefs?.();
            onClearFolderRefs?.();
            onClearMessageRefs?.();
            onPost?.();
        } catch (error) {
            console.error('Failed to post:', error);
            setSubmitError(error?.message || 'Failed to send message.');
        } finally {
            setUploadProgress(null);
            uploadController.current = null;
            setLoading(false);
        }
    };

    const handleKeyDown = (e) => {
        if (shouldStartSpeechPushToTalk(e, content, { searchMode, available: speechAvailable && !loading, active: !!speechRef.current })) {
            e.preventDefault(); startSpeech(); speechHeld.current = true; return;
        }
        if (speechHeld.current && (e.key === ' ' || e.code === 'Space')) { e.preventDefault(); return; }
        if (!searchMode && mentionMatches.length) {
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                setMentionIndex(index => (index + (e.key === 'ArrowDown' ? 1 : -1) + mentionMatches.length) % mentionMatches.length);
                return;
            }
            if ((e.key === 'Enter' && !e.shiftKey) || e.key === 'Tab') {
                e.preventDefault(); acceptMention(mentionMatches[mentionIndex] || mentionMatches[0]); return;
            }
            if (e.key === 'Escape') { e.preventDefault(); setMentionRange(null); return; }
        }
        if (searchMode && e.key === 'Escape') {
            e.preventDefault();
            setSearchText('');
            onExitSearch?.();
            return;
        }
        // Slash autocomplete navigation
        if (showSlash && slashMatches.length > 0) {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                setSlashIndex((i) => (i + 1) % slashMatches.length);
                return;
            }
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                setSlashIndex((i) => (i - 1 + slashMatches.length) % slashMatches.length);
                return;
            }
            if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
                e.preventDefault();
                acceptSlashCommand(slashMatches[slashIndex]);
                return;
            }
            if (e.key === 'Escape') {
                e.preventDefault();
                setShowSlash(false);
                setSlashMatches([]);
                return;
            }
        }
        if (!searchMode && (e.key === 'ArrowUp' || e.key === 'ArrowDown') && !e.metaKey && !e.ctrlKey && !e.altKey && !e.shiftKey) {
            const textarea = textareaRef.current;
            if (!textarea) return;
            const value = textarea.value || '';
            const atStart = textarea.selectionStart === 0 && textarea.selectionEnd === 0;
            const atEnd = textarea.selectionStart === value.length && textarea.selectionEnd === value.length;
            if ((e.key === 'ArrowUp' && atStart) || (e.key === 'ArrowDown' && atEnd)) {
                const history = historyRef.current;
                if (!history.length) return;
                e.preventDefault();
                let idx = historyIndexRef.current;
                if (e.key === 'ArrowUp') {
                    if (idx === -1) {
                        historyDraftRef.current = value;
                        idx = history.length - 1;
                    } else if (idx > 0) {
                        idx -= 1;
                    }
                    historyIndexRef.current = idx;
                    updateValue(history[idx] || '');
                } else {
                    if (idx === -1) return;
                    if (idx < history.length - 1) {
                        idx += 1;
                        historyIndexRef.current = idx;
                        updateValue(history[idx] || '');
                    } else {
                        historyIndexRef.current = -1;
                        updateValue(historyDraftRef.current || '');
                        historyDraftRef.current = '';
                    }
                }
                requestAnimationFrame(() => {
                    const target = textareaRef.current;
                    if (!target) return;
                    const len = target.value.length;
                    target.selectionStart = len;
                    target.selectionEnd = len;
                });
                return;
            }
        }
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (searchMode) {
                if (searchText.trim()) {
                    onSearch?.(searchText.trim(), { images: searchFilterImages, attachments: searchFilterAttachments, scope: searchScope });
                }
            } else {
                handleSubmit(e.ctrlKey || e.metaKey ? 'steer' : 'auto');
            }
        }
    };

    const addMediaFiles = (files) => {
        const list = Array.from(files || []).filter((file) => file instanceof File && file.name !== '.DS_Store');
        if (!list.length) return;
        setSubmitError('');
        setMediaFiles((current) => [...current, ...list]);
    };

    const handleFileChange = (e) => {
        addMediaFiles(e.target.files);
        e.target.value = '';
    };

    const removeMediaFile = (index) => {
        setSubmitError('');
        setMediaFiles((current) => current.filter((_, idx) => idx !== index));
    };

    const clearAllAttachmentRefs = () => {
        setMediaFiles([]);
        onClearFileRefs?.();
            onClearFolderRefs?.();
        onClearMessageRefs?.();
        setSubmitError('');
    };

    const handleDragEnter = (e) => {
        if (searchMode) return;
        e.preventDefault();
        e.stopPropagation();
        dragCounterRef.current += 1;
        setIsDragActive(true);
    };

    const handleDragLeave = (e) => {
        if (searchMode) return;
        e.preventDefault();
        e.stopPropagation();
        dragCounterRef.current = Math.max(0, dragCounterRef.current - 1);
        if (dragCounterRef.current === 0) setIsDragActive(false);
    };

    const handleDragOver = (e) => {
        if (searchMode) return;
        e.preventDefault();
        e.stopPropagation();
        if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
        setIsDragActive(true);
    };

    const handleComposeDrop = (e) => {
        if (searchMode) return;
        e.preventDefault();
        e.stopPropagation();
        dragCounterRef.current = 0;
        setIsDragActive(false);
        addMediaFiles(e.dataTransfer?.files || []);
    };

    const handlePaste = (e) => {
        if (searchMode) return;
        const items = e.clipboardData?.items;
        if (!items) return;
        const images = [];
        for (const item of items) {
            if (item.kind === 'file') {
                const file = item.getAsFile();
                if (file) images.push(file);
            }
        }
        if (images.length > 0) {
            e.preventDefault();
            addMediaFiles(images);
        }
    };

    const handleInput = (e) => {
        cancelSpeech();
        const value = e.target.value;
        updateValue(value);
        const range = !searchMode ? sessionMentionQuery(value, e.target.selectionStart) : null;
        setMentionRange(range); setMentionIndex(0);
        if (range) setShowSlash(false);
    };

    const consumedPrefill = useRef(null);
    useEffect(() => {
        if (!prefillRequest || consumedPrefill.current === prefillRequest || prefillRequest.sessionId !== sessionId || loading || searchMode) return;
        consumedPrefill.current = prefillRequest;
        cancelSpeech();
        // Insert, never submit or discard an existing draft, media or references.
        setContent(text => `${prefillRequest.command} ${text}`);
        setShowSlash(false); setMentionRange(null); setSubmitError('');
        requestAnimationFrame(() => {
            textareaRef.current?.focus();
            textareaRef.current?.setSelectionRange(prefillRequest.command.length + 1, prefillRequest.command.length + 1);
            resizeTextarea();
        });
    }, [prefillRequest, sessionId, loading, searchMode]);

    const handleLocation = () => {
        if (!navigator.geolocation) {
            alert('Geolocation is not available in this browser.');
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                const { latitude, longitude, accuracy } = pos.coords;
                const coords = `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
                const accuracyLabel = Number.isFinite(accuracy) ? ` ±${Math.round(accuracy)}m` : '';
                const mapLink = `https://maps.google.com/?q=${latitude},${longitude}`;
                const snippet = `Location: ${coords}${accuracyLabel} ${mapLink}`;
                appendToValue(snippet);
            },
            (err) => {
                const message = err?.message || 'Unable to retrieve location.';
                alert(`Location error: ${message}`);
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    };

    useEffect(() => {
        if (!showModelPopup) return;
        let disposed = false;
        setLoadingModels(true);
        setModelOptions([]);
        setSessionCatalog(null);
        setModelCatalogError('');
        getSessionModels(sessionId)
            .then((payload) => {
                if (disposed) return;
                setSessionCatalog(payload);
                setModelOptions(payload.available ? payload.models.map(item => `${item.provider}/${item.id}`) : []);
            })
            .catch((error) => {
                if (disposed) return;
                console.warn('Failed to load model list:', error);
                setModelCatalogError(error.message || 'Unable to load models');
                setModelOptions([]);
            })
            .finally(() => { if (!disposed) setLoadingModels(false); });
        return () => { disposed = true; };
    }, [showModelPopup, activeModel, sessionId, modelRefresh]);

    useEffect(() => {
        if (searchMode) setShowModelPopup(false);
    }, [searchMode]);

    useEffect(() => {
        if (!showModelPopup) return;
        const onPointerDown = (event) => {
            const popup = modelPopupRef.current;
            const hint = modelHintRef.current;
            const target = event.target;
            if (popup && popup.contains(target)) return;
            if (hint && hint.contains(target)) return;
            setShowModelPopup(false);
        };
        document.addEventListener('pointerdown', onPointerDown);
        return () => document.removeEventListener('pointerdown', onPointerDown);
    }, [showModelPopup]);

    return html`
        <div class="compose-box" data-testid="compose-box">
            <div class="compose-resize-handle" ...${resizeHandleProps}></div>
            ${searchMode && html`<div class="compose-search-filters">
                <label class="compose-search-scope-wrap" title="Search scope">
                    <select class="compose-search-scope-select" aria-label="Search scope" value=${searchScope} onChange=${e => setSearchScope(e.currentTarget.value)}>
                        <option value="current">Current session</option>
                        <option value="root">Branch family</option>
                        <option value="all">All sessions</option>
                    </select>
                </label>
                <label class="compose-search-filter-wrap" title="Only messages with images">
                    <input type="checkbox" checked=${searchFilterImages} onChange=${() => setSearchFilterImages(v => !v)} />
                    <span class="compose-search-filter-label">Images</span>
                </label>
                <label class="compose-search-filter-wrap" title="Only messages with attachments">
                    <input type="checkbox" checked=${searchFilterAttachments} onChange=${() => setSearchFilterAttachments(v => !v)} />
                    <span class="compose-search-filter-label">Attachments</span>
                </label>
            </div>`}
            ${uploadProgress && html`<div class="compose-inline-status compose-upload-status" role="status" aria-live="polite" data-testid="compose-upload-status">
                <div class="compose-inline-status-row">
                    <div class="compose-inline-status-spinner" aria-hidden="true"></div>
                    <span class="compose-inline-status-title">${`Uploading ${uploadProgress.current}/${uploadProgress.total}: ${uploadProgress.name}`}</span>
                    <span class="compose-inline-status-elapsed">${uploadProgress.percent}%</span>
                    <button type="button" onClick=${() => uploadController.current?.abort()}>Cancel upload</button>
                </div>
                <div class="upload-progress-bar" role="progressbar" aria-label="Attachment upload progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow=${uploadProgress.percent}>
                    <div class="upload-progress-fill" style=${`width:${uploadProgress.percent}%`}></div>
                </div>
            </div>`}
            ${submitError && html`
                <div class="compose-inline-status compose-submit-error" role="alert" aria-live="assertive"><div class="compose-inline-status-detail">${submitError}</div></div>
            `}
            ${!searchMode && html`<${FollowupQueue} items=${queuedFollowups} onRemove=${onQueueRemove} onSteer=${onQueueSteer} onReorder=${onQueueReorder} />`}
            <div
                class=${`compose-input-wrapper${isDragActive ? ' drag-active' : ''}`}
                onDragEnter=${handleDragEnter}
                onDragOver=${handleDragOver}
                onDragLeave=${handleDragLeave}
                onDrop=${handleComposeDrop}
            >
                ${sessionPicker}
                ${sessionTrigger && html`<div class="compose-session-trigger-group compose-session-trigger-top">${sessionTrigger}</div>`}
                <div class="compose-input-main">
                    ${!searchMode && html`<${AgentCapabilities} agent=${defaultAgent} />`}
                    ${!searchMode && isCompacting && html`<div class="compose-inline-status" role="status" aria-live="polite"><span class="compose-session-status-pill compacting">Compacting context…</span></div>`}
                    ${speechState.kind !== 'idle' && html`<div class=${`compose-inline-status compose-speech-status compose-speech-status-${speechState.kind}`} role="status" aria-live="polite"><div class="compose-inline-status-row"><span class="compose-inline-status-dot" aria-hidden="true"></span><span class="compose-inline-status-title">${speechState.kind === 'listening' ? 'Listening…' : speechState.kind === 'requesting_permission' ? 'Requesting microphone permission…' : 'Speech input error'}</span></div>${speechState.detail && html`<div class="compose-inline-status-detail">${speechState.detail}</div>`}</div>`}
                    ${(folderRefs.length > 0 || fileRefs.length > 0 || mediaFiles.length > 0 || messageRefs.length > 0) && html`
                        <div class="compose-file-refs">
                            ${messageRefs.map(id => html`<${FilePill} key=${'message-' + id} prefix="compose" icon="message" label=${'msg:' + id} title=${'Message ' + id} removeTitle="Remove message reference" onRemove=${() => onRemoveMessageRef?.(id)} />`)}
                            ${folderRefs.map(path => html`<${FilePill} key=${'folder-' + path} prefix="compose" icon="folder" label=${path.split('/').pop() || path} title=${path} removeTitle="Remove folder" onRemove=${() => onRemoveFolderRef?.(path)} />`)}
                            ${fileRefs.map(path => html`<${FilePill} key=${'file-' + path} prefix="compose" label=${path.split('/').pop() || path} title=${path} removeTitle="Remove file" onRemove=${() => onRemoveFileRef?.(path)} />`)}
                            ${mediaFiles.map((file, index) => html`<${FilePill} key=${file.name + index} prefix="compose" label=${file.name || `attachment-${index + 1}`} removeTitle="Remove attachment" onRemove=${() => removeMediaFile(index)} />`)}
                            <button
                                type="button"
                                class="compose-clear-attachments-btn"
                                onClick=${clearAllAttachmentRefs}
                                title="Clear all attachments and references"
                                aria-label="Clear all attachments and references"
                            >
                                Clear all
                            </button>
                        </div>
                    `}
                    <textarea
                        ref=${textareaRef}
                        placeholder=${searchMode ? "Search (Enter to run)..." : "Message (Enter to send, Shift+Enter for newline)..."}
                        value=${searchMode ? searchText : content}
                        onInput=${handleInput}
                        onKeyDown=${handleKeyDown}
                        onPaste=${handlePaste}
                        onFocus=${onFocus}
                        onClick=${onFocus}
                        disabled=${loading}
                        rows="1"
                    />
                    ${mentionMatches.length > 0 && html`<div class="slash-autocomplete" role="listbox" aria-label="Session mentions">
                        ${mentionMatches.map((item, index) => html`<div key=${item.id} class=${`slash-item${index === mentionIndex ? ' active' : ''}`} role="option" aria-selected=${index === mentionIndex} onMouseDown=${e => { e.preventDefault(); acceptMention(item); }} onMouseEnter=${() => setMentionIndex(index)}><span class="slash-name">@${item.name}</span><span class="slash-desc">${item.id}</span></div>`)}
                    </div>`}
                    ${showSlash && slashMatches.length > 0 && html`
                        <div class="slash-autocomplete" ref=${slashRef}>
                            ${slashMatches.map((cmd, i) => html`
                                <div
                                    key=${cmd.name}
                                    class=${`slash-item${i === slashIndex ? ' active' : ''}`}
                                    onMouseDown=${(e) => { e.preventDefault(); acceptSlashCommand(cmd); }}
                                    onMouseEnter=${() => setSlashIndex(i)}
                                >
                                    <span class="slash-name">${cmd.name}</span>
                                    <span class="slash-desc">${cmd.description}</span>
                                </div>
                            `)}
                        </div>
                    `}
                    ${showModelPopup && !searchMode && html`
                        <div class="compose-model-popup compose-model-catalogue" ref=${modelPopupRef} onKeyDown=${modelPickerKeys}>
                            <div class="compose-model-catalogue-header">
                                <label class="compose-model-catalogue-search-label" for="vibes-model-search">Search models</label>
                                <div class="compose-model-catalogue-search-row">
                                    <input id="vibes-model-search" type="search" ref=${modelSearchRef} class="compose-model-catalogue-search" role="combobox" aria-label="Search models" aria-expanded="true" aria-controls="compose-model-results" aria-activedescendant=${highlightedModel ? 'model-option-' + encodeURIComponent(highlightedModel) : undefined} aria-autocomplete="list" value=${modelQuery} placeholder="Search models…" onInput=${e => { setModelQuery(e.target.value); setHighlightedModel(null); }} />
                                    ${modelQuery && html`<button type="button" class="compose-model-catalogue-clear" aria-label="Clear model search" onClick=${() => { setModelQuery(''); modelSearchRef.current?.focus(); }}>×</button>`}
                                </div>
                                <div class="compose-model-catalogue-summary" role="status"><span>${filteredModels.length} ${filteredModels.length === 1 ? 'model' : 'models'}</span>${loadingModels && html`<span>Refreshing…</span>`}</div>
                                ${modelCatalogError && html`<div role="alert">${modelCatalogError}<button type="button" onClick=${() => setModelRefresh(v => v + 1)}>Retry model catalog</button></div>`}
                                ${modelPinError && html`<div role="alert">${modelPinError}</div>`}
                            </div>
                            <div class="compose-model-popup-menu compose-model-catalogue-results" id="compose-model-results" role="listbox" aria-label="Models">
                                ${!loadingModels && filteredModels.length === 0 && html`<div class="compose-model-popup-empty">${modelQuery ? 'No matching models' : 'No models available.'}</div>`}
                                ${!loadingModels && modelGroups.map(group => html`<section class="compose-model-catalogue-section" role="group" aria-label=${group.label}>
                                    <div class="compose-model-catalogue-section-heading"><span>${group.label}</span><span>${group.models.length}</span></div>
                                    ${(group.label === 'Current' || group.label === 'Pinned' ? [{ label: null, models: group.models }] : group.providers).map(provider => html`<div class="compose-model-catalogue-group" role=${provider.label ? 'group' : 'presentation'} aria-label=${provider.label || undefined}>
                                        ${provider.label && html`<div class="compose-model-catalogue-group-heading"><span>${provider.label}</span><span>${provider.models.length}</span></div>`}
                                        ${provider.models.map(modelLabel => {
                                            const model = modelMetadata.get(modelLabel);
                                            const displayName = modelNames.get(modelLabel) || modelLabel;
                                            const context = model?.contextWindow ? (model.contextWindow / 1000).toFixed(0) + 'K context' : null;
                                            return html`<button type="button" id=${'model-option-' + encodeURIComponent(modelLabel)} role="option" aria-selected=${modelLabel === activeModel} aria-label=${modelLabel} aria-description=${displayName + ', ' + (modelPins.includes(modelLabel) ? 'pinned. Alt+Enter to unpin.' : 'not pinned. Alt+Enter to pin.')} aria-keyshortcuts="Alt+Enter" class=${'compose-model-catalogue-option' + (modelLabel === activeModel ? ' selected' : '') + (modelLabel === highlightedModel ? ' focused' : '')} onFocus=${() => setHighlightedModel(modelLabel)} data-model-label=${modelLabel} disabled=${switchingModel} onMouseDown=${e => e.preventDefault()} onMouseEnter=${() => setHighlightedModel(modelLabel)} onClick=${() => handleSelectModel(modelLabel)}>
                                                <span class=${'compose-model-catalogue-pin' + (modelPins.includes(modelLabel) ? ' pinned' : '')} role="button" aria-pressed=${modelPins.includes(modelLabel)} aria-label=${(modelPins.includes(modelLabel) ? 'Unpin model ' : 'Pin model ') + modelLabel} onClick=${e => { e.preventDefault(); e.stopPropagation(); toggleModelPin(modelLabel); }}>${modelPins.includes(modelLabel) ? '★' : '☆'}</span>
                                                <span class="compose-model-catalogue-option-content"><span class="compose-model-catalogue-option-primary"><span class="compose-model-catalogue-option-name">${displayName}</span></span>
                                                    ${displayName !== modelLabel && html`<span class="compose-model-catalogue-option-key">${modelLabel}</span>`}
                                                    ${(model?.reasoning || context) && html`<span class="compose-model-catalogue-option-badges">${context && html`<span class="compose-model-catalogue-badge">${context}</span>`}${model?.reasoning && html`<span class="compose-model-catalogue-badge">reasoning</span>`}</span>`}
                                                </span>
                                            </button>`;
                                        })}
                                    </div>`)}
                                </section>`)}
                            </div>
                            <dialog key="model-settings" ref=${modelSettingsRef} onCancel=${() => setModelSettingsOpen(false)} onClose=${() => setModelSettingsOpen(false)} class="model-settings-dialog" aria-label="Models settings" onKeyDown=${event => event.stopPropagation()} onClick=${event => event.stopPropagation()}>
                                <h2>Models settings</h2>
                                <button type="button" disabled=${loadingModels} onClick=${() => { setModelRefresh(value => value + 1); setModelSettingsOpen(false); modelSettingsRef.current?.close(); }}>Refresh model catalog</button>
                                <button type="button" disabled=${switchingModel || loadingModels || modelOptions.length === 0} onClick=${() => { setModelSettingsOpen(false); modelSettingsRef.current?.close(); void handleCycleModel(); }}>Next model</button>
                                <p>Browser pins: ${modelPins.length ? modelPins.join(', ') : 'None'}</p>
                                <p>Provider credentials and model defaults are not managed here. Catalogue availability does not verify provider authentication.</p>
                                <p>Load replaces browser pins. Save replaces instance pins only against the version last loaded.</p>
                                <button type="button" disabled=${pinSyncBusy} onClick=${() => syncInstancePins(false)}>Load instance pins</button>
                                <button type="button" disabled=${pinSyncBusy || !instancePinsLoaded} onClick=${() => syncInstancePins(true)}>Save instance pins</button>
                                ${modelSettingsOpen && pinSyncStatus && html`<div role="status">${pinSyncStatus}</div>`}
                                <button type="button" onClick=${() => { setModelSettingsOpen(false); modelSettingsRef.current?.close(); }}>Close Models settings</button>
                            </dialog>
                            <div class="compose-model-catalogue-footer">
                                <div class="compose-model-catalogue-footer-start">
                                    ${!loadingModels && sessionCatalog?.thinking_levels?.length > 0 && html`<label class="compose-model-catalogue-thinking"><span>Thinking</span>
                                        <select aria-label="Select thinking level" value=${thinkingLevel || ''} disabled=${switchingModel} onChange=${event => handleCycleThinking(event.target.value)}>
                                            ${sessionCatalog.thinking_levels.map(level => html`<option value=${level}>${level}</option>`)}
                                        </select>
                                    </label>`}
                                </div>
                                <button type="button" class="compose-model-popup-btn primary" onClick=${() => { setModelSettingsOpen(true); modelSettingsRef.current?.showModal(); }}>Open Models settings</button>
                            </div>
                        </div>
                    `}
                </div>
                <div class="compose-footer">
                    ${!searchMode && (activeModel || supportsThinking || usageMeta.label || contextUsage?.compactCommand || (contextUsage && contextUsage.percent != null)) && html`
                        <div class="compose-meta-row">
                            ${(activeModel || supportsThinking || usageMeta.label) && html`<div class="compose-model-meta">
                            ${activeModel && html`
                                <button type="button" ref=${modelHintRef}
                                    class="compose-model-hint compose-model-hint-btn"
                                    title=${switchingModel ? 'Switching model…' : `Current model: ${modelHintLabel} (tap to open model picker)`}
                                    aria-label="Open model picker"
                                    onClick=${toggleModelPopup}
                                    disabled=${loading || switchingModel}
                                >
                                    ${switchingModel ? 'Switching…' : modelHintLabel}
                                </button>
                            `}
                            <div class="compose-model-meta-subline">
                            ${usageMeta.label && html`<span class="compose-model-usage-hint" title=${usageMeta.title} aria-label=${usageMeta.title}>${usageMeta.label}</span>`}
                            ${supportsThinking && html`
                                <button type="button" class="compose-thinking-pill compose-model-usage-hint"
                                    aria-label="Cycle thinking level"
                                    title=${switchingModel ? 'Switching thinking level…' : `${thinkingLabel} (tap to cycle)`}
                                    onClick=${() => { void handleCycleThinking(); }}
                                    disabled=${loading || switchingModel}
                                >
                                    ${thinkingLevel || 'thinking'}
                                </button>
                            `}
                            </div>
                            </div>`}
                            ${contextUsage && (contextUsage.percent != null || contextUsage.compactCommand) && html`
                                <${ContextPie} usage=${contextUsage} onCompact=${compact} disabled=${loading || agentBusy || isCompacting} compacting=${isCompacting} />
                            `}
                        </div>
                    `}
                <div class="compose-actions ${searchMode ? 'search-mode' : ''}">
                    ${onOpenQuickActions && html`<button type="button" class="icon-btn quick-actions-toggle" aria-label="Quick actions" title="Quick actions (or type while focused on the timeline)" disabled=${loading} onClick=${onOpenQuickActions}>
                        <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2 4 14h7l-1 8 10-12h-7z"/></svg>
                    </button>`}
                    <button type="button" class="icon-btn search-toggle"
                        onClick=${searchMode ? onExitSearch : onEnterSearch}
                        title=${searchMode ? "Close search" : "Search"}
                    >
                        ${searchMode ? html`
                            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M18 6L6 18M6 6l12 12"/>
                            </svg>
                        ` : html`
                            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="11" cy="11" r="8"/>
                                <path d="M21 21l-4.35-4.35"/>
                            </svg>
                        `}
                    </button>
                    ${canShareLocation && !searchMode && html`
                        <button type="button" class="icon-btn location-btn"
                            onClick=${handleLocation}
                            title="Share location"
                            disabled=${loading}
                        >
                            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="12" cy="12" r="10" />
                                <path d="M12 2a14 14 0 0 1 0 20a14 14 0 0 1 0-20" />
                                <path d="M2 12h20" />
                            </svg>
                        </button>
                    `}
                    ${speechAvailable && !searchMode && html`<button type="button" class=${`compose-icon-btn compose-mic-btn${speechActive ? ' active' : ''}`} title="Speech input (hold Space in an empty composer to talk; browser recognition may use a remote service)" aria-label=${speechActive ? 'Stop speech input' : 'Start speech input'} aria-pressed=${speechActive} disabled=${loading} onPointerDown=${handleSpeechPointerDown} onPointerUp=${releaseSpeechPointer} onPointerCancel=${releaseSpeechPointer} onLostPointerCapture=${releaseSpeechPointer} onClick=${event => {
                        if (suppressSpeechClick.current && event.detail !== 0) { suppressSpeechClick.current = false; return; }
                        suppressSpeechClick.current = false;
                        if (speechActive) speechRef.current?.stop(); else startSpeech();
                    }}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0014 0v-2M12 19v3M8 22h8"/></svg></button>`}
                    ${notificationsAvailable && !searchMode && html`
                        <button type="button" class=${`icon-btn notification-btn${notificationActive ? ' active' : ''}`}
                            onClick=${onToggleNotifications}
                            title=${notificationTitle}
                            >
                            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
                                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                            </svg>
                        </button>
                    `}
                    ${(!searchMode || agentBusy) && html`
                        ${!searchMode && html`<label class="icon-btn" title="Attach files">
                            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                            <input type="file" multiple hidden onChange=${handleFileChange} />
                        </label>`}
                        <div class="compose-send-stack">
                            ${!searchMode && html`<button type="button" class=${`icon-btn send-btn${agentBusy ? ' queue-mode' : ''}`}
                                data-testid="send-button"
                                onClick=${() => handleSubmit('auto')}
                                disabled=${!canSend}
                                title="Send (Enter); steer with Ctrl/Cmd+Enter"
                                aria-label="Send message"
                            >
                                <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
                            </button>`}
                            ${agentBusy && html`
                                <button type="button" class="icon-btn send-btn abort-mode"
                                    data-testid="stop-button"
                                    onClick=${handleAbort}
                                    title=${aborting ? 'Cancelling current turn…' : 'Cancel current turn'}
                                    aria-label="Cancel current turn"
                                    disabled=${aborting || !activeTurnId}
                                    aria-busy=${aborting}
                                >
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect class="compose-turn-stop-icon" x="6" y="6" width="12" height="12" rx="2" /></svg>
                                </button>
                            `}
                        </div>
                    `}
                </div>
                </div>
            </div>
        </div>
    `;
}
