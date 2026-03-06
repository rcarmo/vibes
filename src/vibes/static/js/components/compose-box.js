import { html, useRef, useState } from '../vendor/preact-htm.js';
import { sendAgentMessage, uploadMedia } from '../api.js';

export function ComposeBox({
    onPost,
    onFocus,
    searchMode,
    onSearch,
    onEnterSearch,
    onExitSearch,
    fileRefs = [],
    onRemoveFileRef,
    onClearFileRefs,
    activeModel = null,
    onModelChange,
    notificationsEnabled = false,
    notificationPermission = 'default',
    onToggleNotifications,
}) {
    const [content, setContent] = useState('');
    const [searchText, setSearchText] = useState('');
    const [loading, setLoading] = useState(false);
    const [mediaFiles, setMediaFiles] = useState([]);
    const [isDragActive, setIsDragActive] = useState(false);
    const textareaRef = useRef(null);
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
        if (typeof window === 'undefined') return [];
        try {
            const raw = localStorage.getItem('vibes_compose_history');
            if (!raw) return [];
            const parsed = JSON.parse(raw);
            if (!Array.isArray(parsed)) return [];
            return normaliseHistory(parsed);
        } catch {
            return [];
        }
    };
    const saveHistory = (history) => {
        if (typeof window === 'undefined') return;
        try {
            localStorage.setItem('vibes_compose_history', JSON.stringify(history));
        } catch {
            // ignore
        }
    };
    const historyRef = useRef(loadHistory());
    const historyIndexRef = useRef(-1);
    const historyDraftRef = useRef('');
    const canSend = !loading && (content.trim() || mediaFiles.length > 0 || fileRefs.length > 0);
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

    const resizeTextarea = () => {
        const textarea = textareaRef.current;
        if (!textarea) return;
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
    };

    const updateValue = (value) => {
        if (searchMode) {
            setSearchText(value);
        } else {
            setContent(value);
        }
        requestAnimationFrame(resizeTextarea);
    };

    const appendToValue = (snippet) => {
        const current = searchMode ? searchText : content;
        const prefix = current && !current.endsWith('\n') ? '\n' : '';
        const next = `${current}${prefix}${snippet}`.trimStart();
        updateValue(next);
    };

    const handleSubmit = async () => {
        if (!content.trim() && mediaFiles.length === 0 && fileRefs.length === 0) return;

        setLoading(true);
        try {
            const mediaIds = [];
            for (const file of mediaFiles) {
                const result = await uploadMedia(file);
                mediaIds.push(result.id);
            }

            const baseContent = content.trim();
            const fileBlock = fileRefs.length
                ? `Files:\n${fileRefs.map((path) => `- ${path}`).join('\n')}`
                : '';
            const mediaBlock = mediaIds.length
                ? `Images:\n${mediaIds.map((id, index) => {
                    const file = mediaFiles[index];
                    const label = file?.name || `image-${index + 1}`;
                    return `- attachment:${id} (${label})`;
                }).join('\n')}`
                : '';
            const message = [baseContent, fileBlock, mediaBlock].filter(Boolean).join('\n\n');

            const response = await sendAgentMessage('default', message, null, mediaIds);
            if (response?.command?.model_label && typeof onModelChange === 'function') {
                onModelChange(response.command.model_label);
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

            setContent('');
            setMediaFiles([]);
            onClearFileRefs?.();
            onPost?.();
        } catch (error) {
            console.error('Failed to post:', error);
            alert('Failed to post: ' + error.message);
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (e) => {
        if (searchMode && e.key === 'Escape') {
            e.preventDefault();
            setSearchText('');
            onExitSearch?.();
            return;
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
                    onSearch?.(searchText.trim());
                }
            } else {
                handleSubmit();
            }
        }
    };

    const addMediaFiles = (files) => {
        const list = Array.from(files || []).filter((file) => file && file.type && file.type.startsWith('image/'));
        if (!list.length) return;
        setMediaFiles((current) => [...current, ...list]);
    };

    const handleFileChange = (e) => {
        addMediaFiles(e.target.files);
        e.target.value = '';
    };

    const removeMediaFile = (index) => {
        setMediaFiles((current) => current.filter((_, idx) => idx !== index));
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

    const handleInput = (e) => {
        const value = e.target.value;
        updateValue(value);
    };

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

    return html`
        <div class="compose-box">
            <div
                class=${`compose-input-wrapper${isDragActive ? ' drag-active' : ''}`}
                onDragEnter=${handleDragEnter}
                onDragOver=${handleDragOver}
                onDragLeave=${handleDragLeave}
                onDrop=${handleComposeDrop}
            >
                <div class="compose-input-main">
                    ${!searchMode && (fileRefs.length > 0 || mediaFiles.length > 0) && html`
                        <div class="compose-file-refs">
                            ${fileRefs.map((path) => {
                                const label = path.split('/').pop() || path;
                                return html`
                                    <span class="compose-file-pill" title=${path}>
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                            <polyline points="14 2 14 8 20 8"/>
                                        </svg>
                                        <span class="compose-file-name">${label}</span>
                                        <button
                                            class="compose-file-remove"
                                            onClick=${(event) => {
                                                event.preventDefault();
                                                event.stopPropagation();
                                                onRemoveFileRef?.(path);
                                            }}
                                            title="Remove file"
                                            type="button"
                                        >
                                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                                <path d="M18 6L6 18M6 6l12 12"/>
                                            </svg>
                                        </button>
                                    </span>
                                `;
                            })}
                            ${mediaFiles.map((file, index) => {
                                const label = file?.name || `image-${index + 1}`;
                                return html`
                                    <span key=${label + index} class="compose-file-pill" title=${label}>
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                            <polyline points="14 2 14 8 20 8"/>
                                        </svg>
                                        <span class="compose-file-name">${label}</span>
                                        <button
                                            class="compose-file-remove"
                                            onClick=${(event) => {
                                                event.preventDefault();
                                                event.stopPropagation();
                                                removeMediaFile(index);
                                            }}
                                            title="Remove image"
                                            type="button"
                                        >
                                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                                <path d="M18 6L6 18M6 6l12 12"/>
                                            </svg>
                                        </button>
                                    </span>
                                `;
                            })}
                        </div>
                    `}
                    <textarea
                        ref=${textareaRef}
                        placeholder=${searchMode ? "Search (Enter to run)..." : "Message (Enter to send, Shift+Enter for newline)..."}
                        value=${searchMode ? searchText : content}
                        onInput=${handleInput}
                        onKeyDown=${handleKeyDown}
                        onFocus=${onFocus}
                        onClick=${onFocus}
                        disabled=${loading}
                        rows="1"
                    />
                    ${!searchMode && activeModel && html`
                        <span class="compose-model-hint" title=${activeModel}>${activeModel}</span>
                    `}
                </div>
                <div class="compose-actions ${searchMode ? 'search-mode' : ''}">
                    <button
                        class="icon-btn search-toggle"
                        onClick=${searchMode ? onExitSearch : onEnterSearch}
                        title=${searchMode ? "Close search" : "Search"}
                    >
                        ${searchMode ? html`
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M18 6L6 18M6 6l12 12"/>
                            </svg>
                        ` : html`
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="11" cy="11" r="8"/>
                                <path d="M21 21l-4.35-4.35"/>
                            </svg>
                        `}
                    </button>
                    ${canShareLocation && !searchMode && html`
                        <button
                            class="icon-btn location-btn"
                            onClick=${handleLocation}
                            title="Share location"
                            type="button"
                            disabled=${loading}
                        >
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="12" cy="12" r="10" />
                                <path d="M12 2a14 14 0 0 1 0 20a14 14 0 0 1 0-20" />
                                <path d="M2 12h20" />
                            </svg>
                        </button>
                    `}
                    ${notificationsAvailable && !searchMode && html`
                        <button
                            class=${`icon-btn notification-btn${notificationActive ? ' active' : ''}`}
                            onClick=${onToggleNotifications}
                            title=${notificationTitle}
                            type="button"
                        >
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
                                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                            </svg>
                        </button>
                    `}
                    ${!searchMode && html`
                        <label class="icon-btn" title="Attach image">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                            <input type="file" accept="image/*" multiple hidden onChange=${handleFileChange} />
                        </label>
                        <button
                            class="icon-btn send-btn"
                            onClick=${handleSubmit}
                            disabled=${!canSend}
                            title="Send (Ctrl+Enter)"
                        >
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
                        </button>
                    `}
                </div>
            </div>
        </div>
    `;
}
