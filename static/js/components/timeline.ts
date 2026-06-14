// @ts-nocheck
import { html, useCallback, useEffect, useRef, useState } from '../vendor/preact-htm.js';
import { getMediaInfo, getMediaUrl, getThumbnailUrl } from '../api.ts';
import {
    escapeRegex,
    extractAttachmentRefs,
    extractFileRefs,
    extractMessageRefs,
    fallbackAvatarInfo,
    formatFileSize,
    formatTimestamp,
    getDisplayContent,
    getMimeIcon,
    sanitizeUrl,
} from '../features/timeline/timeline-utils.ts';


function highlightHtml(htmlStr, query) {
    if (!htmlStr || !query) return htmlStr;
    const terms = String(query).trim().split(/\s+/).filter(Boolean);
    if (terms.length === 0) return htmlStr;

    const escapedTerms = terms.map(escapeRegex).sort((a, b) => b.length - a.length);
    const pattern = new RegExp(`(${escapedTerms.join('|')})`, 'gi');
    const matcher = new RegExp(`^(${escapedTerms.join('|')})$`, 'i');

    const doc = new DOMParser().parseFromString(htmlStr, 'text/html');
    const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    let node;
    while ((node = walker.nextNode())) nodes.push(node);

    for (const textNode of nodes) {
        const value = textNode.nodeValue;
        if (!value || !pattern.test(value)) { pattern.lastIndex = 0; continue; }
        pattern.lastIndex = 0;
        const parent = textNode.parentElement;
        if (parent && parent.closest('code, pre, script, style')) continue;

        const parts = value.split(pattern).filter((part) => part !== '');
        if (parts.length === 0) continue;
        const frag = doc.createDocumentFragment();
        for (const part of parts) {
            if (matcher.test(part)) {
                const mark = doc.createElement('mark');
                mark.className = 'search-highlight-term';
                mark.textContent = part;
                frag.appendChild(mark);
            } else {
                frag.appendChild(doc.createTextNode(part));
            }
        }
        textNode.parentNode.replaceChild(frag, textNode);
    }

    return doc.body.innerHTML;
}

const CODE_COPY_RESET_MS = 2000;
const COPY_ICON_SVG = `
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
        <rect x="5" y="3" width="8" height="10" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.5"></rect>
        <path d="M3 11V4.5C3 3.67 3.67 3 4.5 3H10" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"></path>
    </svg>
`;
const COPY_SUCCESS_SVG = `
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
        <path d="M3.5 8.5 6.5 11.5 12.5 4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>
    </svg>
`;
const COPY_ERROR_SVG = `
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
        <path d="M4.5 4.5 11.5 11.5M11.5 4.5 4.5 11.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"></path>
    </svg>
`;

async function copyCodeText(text) {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch {
            // Fall through to the textarea fallback.
        }
    }
    try {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.setAttribute('readonly', '');
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        textarea.setSelectionRange(0, textarea.value.length);
        const copied = document.execCommand('copy');
        document.body.removeChild(textarea);
        return copied;
    } catch {
        return false;
    }
}

function enhanceCodeBlocks(container) {
    if (!container) return () => {};
    const blocks = Array.from(container.querySelectorAll('pre')).filter((pre) => pre.querySelector('code'));
    if (blocks.length === 0) return () => {};

    const resetTimers = new Map();
    const cleanups = [];

    const setButtonState = (button, state) => {
        const nextState = state || 'idle';
        button.dataset.copyState = nextState;
        if (nextState === 'success') {
            button.innerHTML = COPY_SUCCESS_SVG;
            button.setAttribute('aria-label', 'Copied');
            button.setAttribute('title', 'Copied');
            button.classList.add('is-success');
            button.classList.remove('is-error');
        } else if (nextState === 'error') {
            button.innerHTML = COPY_ERROR_SVG;
            button.setAttribute('aria-label', 'Copy failed');
            button.setAttribute('title', 'Copy failed');
            button.classList.add('is-error');
            button.classList.remove('is-success');
        } else {
            button.innerHTML = COPY_ICON_SVG;
            button.setAttribute('aria-label', 'Copy code');
            button.setAttribute('title', 'Copy code');
            button.classList.remove('is-success', 'is-error');
        }
    };

    blocks.forEach((pre) => {
        const wrapper = document.createElement('div');
        wrapper.className = 'post-code-block';
        pre.parentNode?.insertBefore(wrapper, pre);
        wrapper.appendChild(pre);

        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'post-code-copy-btn';
        setButtonState(button, 'idle');
        wrapper.appendChild(button);

        const handleCopyClick = async (event) => {
            event.preventDefault();
            event.stopPropagation();
            const code = pre.querySelector('code');
            const ok = await copyCodeText(code?.textContent || '');
            setButtonState(button, ok ? 'success' : 'error');
            const existingTimer = resetTimers.get(button);
            if (existingTimer) clearTimeout(existingTimer);
            const timer = setTimeout(() => {
                setButtonState(button, 'idle');
                resetTimers.delete(button);
            }, CODE_COPY_RESET_MS);
            resetTimers.set(button, timer);
        };

        button.addEventListener('click', handleCopyClick);
        cleanups.push(() => {
            button.removeEventListener('click', handleCopyClick);
            const timer = resetTimers.get(button);
            if (timer) clearTimeout(timer);
            if (wrapper.parentNode) {
                wrapper.parentNode.insertBefore(pre, wrapper);
                wrapper.remove();
            }
        });
    });

    return () => {
        cleanups.forEach((cleanup) => cleanup());
    };
}

function ImageModal({ src, onClose }) {
    const [scale, setScale] = useState(1);
    const [translate, setTranslate] = useState({ x: 0, y: 0 });
    const [dragging, setDragging] = useState(false);
    const dragStart = useRef({ x: 0, y: 0 });
    const imgRef = useRef(null);

    useEffect(() => {
        const handleEsc = (e) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('keydown', handleEsc);
        return () => document.removeEventListener('keydown', handleEsc);
    }, [onClose]);

    const handleWheel = (e) => {
        e.preventDefault();
        const delta = e.deltaY > 0 ? 0.9 : 1.1;
        setScale((s) => Math.max(0.5, Math.min(10, s * delta)));
    };

    const handlePointerDown = (e) => {
        if (e.button !== 0) return;
        e.stopPropagation();
        setDragging(true);
        dragStart.current = { x: e.clientX - translate.x, y: e.clientY - translate.y };
        e.target.setPointerCapture(e.pointerId);
    };

    const handlePointerMove = (e) => {
        if (!dragging) return;
        setTranslate({ x: e.clientX - dragStart.current.x, y: e.clientY - dragStart.current.y });
    };

    const handlePointerUp = () => setDragging(false);

    const handleDoubleClick = (e) => {
        e.stopPropagation();
        setScale(scale === 1 ? 2 : 1);
        setTranslate({ x: 0, y: 0 });
    };

    const zoomIn = (e) => { e.stopPropagation(); setScale((s) => Math.min(10, s * 1.3)); };
    const zoomOut = (e) => { e.stopPropagation(); setScale((s) => Math.max(0.5, s / 1.3)); };
    const resetZoom = (e) => { e.stopPropagation(); setScale(1); setTranslate({ x: 0, y: 0 }); };

    return html`
        <div class="image-modal" onClick=${onClose} onWheel=${handleWheel}>
            <div class="image-modal-controls" onClick=${(e) => e.stopPropagation()}>
                <button onClick=${zoomOut} title="Zoom out">−</button>
                <button onClick=${resetZoom} title="Reset">${Math.round(scale * 100)}%</button>
                <button onClick=${zoomIn} title="Zoom in">+</button>
                <button onClick=${onClose} title="Close">✕</button>
            </div>
            <img
                ref=${imgRef}
                src=${src}
                alt="Full size"
                class="image-modal-img"
                style=${{ transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`, cursor: dragging ? 'grabbing' : 'grab' }}
                onClick=${(e) => e.stopPropagation()}
                onDblClick=${handleDoubleClick}
                onPointerDown=${handlePointerDown}
                onPointerMove=${handlePointerMove}
                onPointerUp=${handlePointerUp}
                draggable="false"
            />
        </div>
    `;
}

function FileAttachment({ mediaId }) {
    const [info, setInfo] = useState(null);

    useEffect(() => {
        getMediaInfo(mediaId).then(setInfo).catch(() => {});
    }, [mediaId]);

    if (!info) return null;

    const filename = info.filename || 'file';
    const size = info.metadata?.size;
    const sizeStr = size ? formatFileSize(size) : '';

    return html`
        <a href=${getMediaUrl(mediaId)} download=${filename} class="file-attachment" onClick=${(e) => e.stopPropagation()}>
            <svg class="file-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
                <polyline points="10 9 9 9 8 9"/>
            </svg>
            <div class="file-info">
                <span class="file-name">${filename}</span>
                ${sizeStr && html`<span class="file-size">${sizeStr}</span>`}
            </div>
            <svg class="download-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
        </a>
    `;
}

function AnnotationsBadge({ annotations }) {
    if (!annotations) return null;
    const { audience, priority, lastModified } = annotations;
    const formattedLastModified = lastModified ? formatTimestamp(lastModified) : null;
    return html`
        <div class="content-annotations">
            ${audience && audience.length > 0 && html`
                <span class="content-annotation">Audience: ${audience.join(', ')}</span>
            `}
            ${typeof priority === 'number' && html`
                <span class="content-annotation">Priority: ${priority}</span>
            `}
            ${formattedLastModified && html`
                <span class="content-annotation">Updated: ${formattedLastModified}</span>
            `}
        </div>
    `;
}

function ResourceLinkBlock({ block }) {
    const name = block.title || block.name || block.uri;
    const description = block.description;
    const sizeStr = block.size ? formatFileSize(block.size) : '';
    const mimeType = block.mime_type || '';
    const icon = getMimeIcon(mimeType);
    const safeUrl = sanitizeUrl(block.uri);
    return html`
        <a href=${safeUrl || '#'} class="resource-link"
            target=${safeUrl ? "_blank" : undefined}
            rel=${safeUrl ? "noopener noreferrer" : undefined}
            onClick=${(e) => e.stopPropagation()}>
            <div class="resource-link-main">
                <div class="resource-link-header">
                    <span class="resource-link-icon-inline">${icon}</span>
                    <div class="resource-link-title">${name}</div>
                </div>
                ${description && html`<div class="resource-link-description">${description}</div>`}
                <div class="resource-link-meta">
                    ${mimeType && html`<span>${mimeType}</span>`}
                    ${sizeStr && html`<span>${sizeStr}</span>`}
                </div>
            </div>
            <div class="resource-link-icon">↗</div>
        </a>
    `;
}

function ResourceBlock({ block }) {
    const [open, setOpen] = useState(false);
    const title = block.uri || 'Embedded resource';
    const contentText = block.text || '';
    const hasBlob = Boolean(block.data);
    const mimeType = block.mime_type || '';
    return html`
        <div class="resource-embed">
            <button class="resource-embed-toggle" onClick=${(e) => { e.preventDefault(); e.stopPropagation(); setOpen(!open); }}>
                ${open ? '▼' : '▶'} ${title}
            </button>
            ${open && html`
                ${contentText && html`<pre class="resource-embed-content">${contentText}</pre>`}
                ${hasBlob && html`
                    <div class="resource-embed-blob">
                        <span class="resource-embed-blob-label">Embedded blob</span>
                        ${mimeType && html`<span class="resource-embed-blob-meta">${mimeType}</span>`}
                        <button class="resource-embed-blob-btn" onClick=${(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            const blob = new Blob([Uint8Array.from(atob(block.data), (c) => c.charCodeAt(0))], { type: mimeType || 'application/octet-stream' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = title.split('/').pop() || 'resource';
                            a.click();
                            URL.revokeObjectURL(url);
                        }}>Download</button>
                    </div>
                `}
            `}
        </div>
    `;
}

function LinkPreview({ preview }) {
    const bgStyle = preview.image
        ? `background-image: url('${preview.image}')`
        : '';

    return html`
        <a href=${preview.url} class="link-preview ${preview.image ? 'has-image' : ''}" target="_blank" rel="noopener noreferrer" onClick=${(e) => e.stopPropagation()} style=${bgStyle}>
            <div class="link-preview-overlay">
                <div class="link-preview-site">${preview.site_name || new URL(preview.url).hostname}</div>
                <div class="link-preview-title">${preview.title}</div>
                ${preview.description && html`
                    <div class="link-preview-description">${preview.description}</div>
                `}
            </div>
        </a>
    `;
}

function Post({
    post,
    onClick,
    onHashtagClick,
    onMessageRef,
    onScrollToMessage,
    onOpenAttachmentPreview,
    agentName,
    agentAvatarUrl,
    userName,
    userAvatarUrl,
    onDelete,
    isThreadReply,
    isRemoving,
    highlightQuery,
    renderMarkdown,
    renderMermaidDiagrams,
    getAvatarInfo,
    formatTime,
    formatCount,
}) {
    const [zoomedImage, setZoomedImage] = useState(null);
    const contentRef = useRef(null);

    const data = post.data;
    const isAgent = data.type === 'agent_response';
    const resolvedUserName = userName || 'You';
    const displayName = isAgent ? (agentName || 'Agent') : resolvedUserName;
    const backend = data.backend || null;
    const backendLabel = backend?.label || backend?.id || '';
    const backendDetails = [backend?.transport, backend?.model, backend?.mode, backend?.thread_backend_generation ? `gen ${backend.thread_backend_generation}` : '']
        .filter(Boolean)
        .join(' · ');

    const avatarInfo = isAgent
        ? (getAvatarInfo?.(agentName, agentAvatarUrl) || fallbackAvatarInfo(agentName, agentAvatarUrl))
        : (getAvatarInfo?.(resolvedUserName, userAvatarUrl) || fallbackAvatarInfo(resolvedUserName, userAvatarUrl));
    const avatarBgColor = avatarInfo.image ? 'transparent' : avatarInfo.color;
    const formatTimeLabel = formatTime || ((value) => String(value || ''));
    const formatCountLabel = formatCount || ((value) => String(value ?? 0));
    const contentMeta = data.content_meta;
    const isTruncated = Boolean(contentMeta?.truncated);
    const isPreview = Boolean(contentMeta?.preview);
    const isHardTruncated = isTruncated && !isPreview;
    const truncatedInfo = isTruncated
        ? {
            originalLength: Number.isFinite(contentMeta?.original_length)
                ? contentMeta.original_length
                : (data.content ? data.content.length : 0),
            maxLength: Number.isFinite(contentMeta?.max_length) ? contentMeta.max_length : 0,
        }
        : null;

    let displayContent = getDisplayContent(data.content, data.link_previews);

    const handleImageClick = (e, mediaId) => {
        e.stopPropagation();
        setZoomedImage(getMediaUrl(mediaId));
    };

    const [menuOpen, setMenuOpen] = useState(false);
    const menuRef = useRef(null);

    // Close menu on outside click
    useEffect(() => {
        if (!menuOpen) return;
        const close = (e) => {
            if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
        };
        document.addEventListener('click', close, true);
        return () => document.removeEventListener('click', close, true);
    }, [menuOpen]);

    const handleCopyText = (e) => {
        e.stopPropagation();
        const text = contentRef.current?.innerText || displayContent || '';
        navigator.clipboard.writeText(text).catch(() => {});
        setMenuOpen(false);
    };

    const handleCopyMarkdown = (e) => {
        e.stopPropagation();
        navigator.clipboard.writeText(displayContent || '').catch(() => {});
        setMenuOpen(false);
    };

    const handleReply = (e) => {
        e.stopPropagation();
        if (onMessageRef) onMessageRef(String(post.id));
        setMenuOpen(false);
    };

    const handleMenuDelete = (e) => {
        e.stopPropagation();
        onDelete?.(post);
        setMenuOpen(false);
    };

    const resolveInlineAttachments = (content, attachments) => {
        const usedIds = new Set();
        if (!content || attachments.length === 0) {
            return { content, usedIds };
        }

        const replaced = content.replace(/attachment:([^\s)"']+)/g, (match, rawRef, offset, source) => {
            const ref = rawRef.replace(/^\/+/, '');
            const byName = attachments.find(
                (entry) => entry.name && entry.name.toLowerCase() === ref.toLowerCase() && !usedIds.has(entry.id)
            );
            const entry = byName || attachments.find((item) => !usedIds.has(item.id));
            if (!entry) return match;
            usedIds.add(entry.id);
            const prefix = source.slice(Math.max(0, offset - 2), offset);
            if (prefix === '](') {
                return `/media/${entry.id}`;
            }
            return entry.name || 'attachment';
        });

        return { content: replaced, usedIds };
    };

    const imageItems = [];
    const fileIds = [];
    const attachmentEntries = [];
    const resourceLinks = [];
    const resources = [];
    const textAnnotations = [];
    const blocks = data.content_blocks || [];
    const mediaIds = data.media_ids || [];
    let mediaIndex = 0;

    if (blocks.length > 0) {
        blocks.forEach((block) => {
            if (block?.type === 'text' && block.annotations) {
                textAnnotations.push(block.annotations);
            }
            if (block?.type === 'resource_link') {
                resourceLinks.push(block);
            } else if (block?.type === 'resource') {
                resources.push(block);
            } else if (block?.type === 'file') {
                const id = mediaIds[mediaIndex++];
                if (id) {
                    fileIds.push(id);
                    attachmentEntries.push({ id, name: block?.name || block?.filename || block?.title });
                }
            } else if (block?.type === 'image' || !block?.type) {
                const id = mediaIds[mediaIndex++];
                if (id) {
                    imageItems.push({ id, annotations: block?.annotations });
                    attachmentEntries.push({ id, name: block?.name || block?.filename || block?.title });
                }
            }
        });
    } else if (mediaIds.length > 0) {
        mediaIds.forEach((id) => {
            imageItems.push({ id, annotations: null });
            attachmentEntries.push({ id, name: null });
        });
    }

    if ((!displayContent || !displayContent.trim()) && blocks.length > 0) {
        const textParts = [];
        const stack = [...blocks];
        while (stack.length > 0) {
            const item = stack.shift();
            if (!item || typeof item !== 'object') continue;
            if (item.type === 'text' && typeof item.text === 'string') {
                textParts.push(item.text);
            }
            if (Array.isArray(item.content)) {
                stack.push(...item.content);
            } else if (item.content && typeof item.content === 'object') {
                stack.push(item.content);
            }
        }
        const fallbackContent = textParts.join('');
        if (fallbackContent.trim()) {
            displayContent = fallbackContent;
        }
    }

    const { content: cleanedContent, fileRefs } = extractFileRefs(displayContent);
    const { content: cleanedWithMessages, messageRefs } = extractMessageRefs(cleanedContent);
    const { content: cleanedWithAttachments, attachments } = extractAttachmentRefs(cleanedWithMessages);
    displayContent = cleanedWithAttachments;

    if (attachments.length > 0) {
        attachments.forEach((ref) => {
            if (!ref?.id) return;
            const match = attachmentEntries.find((entry) => String(entry.id) === String(ref.id));
            if (match && !match.name) {
                match.name = ref.label;
            }
        });
    }

    const { content: resolvedContent, usedIds } = resolveInlineAttachments(displayContent, attachmentEntries);
    displayContent = resolvedContent;
    const filteredImageItems = imageItems.filter(({ id }) => !usedIds.has(id));
    const filteredFileIds = fileIds.filter((id) => !usedIds.has(id));

    const attachmentPills = attachments.length > 0
        ? attachments.map((ref, idx) => ({
            id: ref.id || `attachment-${idx + 1}`,
            label: ref.label || `attachment-${idx + 1}`,
        }))
        : attachmentEntries.map((entry, idx) => ({
            id: entry.id,
            label: entry.name || `attachment-${idx + 1}`,
        }));

    const shouldRenderContent = Boolean(displayContent?.trim()) && !isHardTruncated;

    useEffect(() => {
        if (contentRef.current && renderMermaidDiagrams) {
            renderMermaidDiagrams(contentRef.current);
        }
    }, [displayContent, renderMermaidDiagrams]);

    useEffect(() => {
        return enhanceCodeBlocks(contentRef.current);
    }, [displayContent, highlightQuery]);

    return html`
        <div id=${`post-${post.id}`} class="post ${isAgent ? 'agent-post' : ''} ${isThreadReply ? 'thread-reply' : ''} ${isRemoving ? 'removing' : ''}" onClick=${onClick}>
            <div class="post-avatar ${isAgent ? 'agent-avatar' : ''} ${avatarInfo.image ? 'has-image' : ''}" style="background-color: ${avatarBgColor}">
                ${avatarInfo.image ? html`<img src=${avatarInfo.image} alt=${displayName} />` : avatarInfo.letter}
            </div>
            <div class="post-body">
                <div class="post-context-menu" ref=${menuRef}>
                    <button
                        class="post-menu-btn"
                        type="button"
                        title="More actions"
                        aria-label="More actions"
                        onClick=${(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); }}
                    >
                        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                            <circle cx="12" cy="5" r="1.5" />
                            <circle cx="12" cy="12" r="1.5" />
                            <circle cx="12" cy="19" r="1.5" />
                        </svg>
                    </button>
                    ${menuOpen && html`
                        <div class="post-menu-dropdown">
                            <button onClick=${handleCopyText}>
                                <svg viewBox="0 0 24 24"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>
                                Copy text
                            </button>
                            <button onClick=${handleCopyMarkdown}>
                                <svg viewBox="0 0 24 24"><path d="M14.59 2.59c-.38-.38-.89-.59-1.42-.59H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8.83c0-.53-.21-1.04-.59-1.41l-4.82-4.83zM15 18H9v-2h6v2zm0-4H9v-2h6v2zm-2-6V3.5L18.5 9H13z"/></svg>
                                Copy as markdown
                            </button>
                            ${onMessageRef && html`
                                <button onClick=${handleReply}>
                                    <svg viewBox="0 0 24 24"><path d="M10 9V5l-7 7 7 7v-4.1c5 0 8.5 1.6 11 5.1-1-5-4-10-11-11z"/></svg>
                                    Reply
                                </button>
                            `}
                            <hr />
                            <button class="danger" onClick=${handleMenuDelete}>
                                <svg viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
                                Delete
                            </button>
                        </div>
                    `}
                </div>
                <div class="post-meta">
                    <span class="post-author">${displayName}</span>
                    ${backendLabel && html`<span class="post-backend" title=${backendDetails ? `${backendLabel} · ${backendDetails}` : backendLabel}>${backendLabel}</span>`}
                    <span class="post-time" onClick=${(e) => {
                        if (onMessageRef) {
                            e.stopPropagation();
                            onMessageRef(String(post.id));
                        }
                    }} style=${onMessageRef ? 'cursor:pointer' : ''}>${formatTimeLabel(post.timestamp)}</span>
                </div>
                ${isHardTruncated && truncatedInfo && html`
                    <div class="post-content truncated">
                        <div class="truncated-title">Message too large to display.</div>
                        <div class="truncated-meta">
                            Original length: ${formatCountLabel(truncatedInfo.originalLength)} chars
                            ${truncatedInfo.maxLength ? html` • Display limit: ${formatCountLabel(truncatedInfo.maxLength)} chars` : ''}
                        </div>
                    </div>
                `}
                ${isPreview && truncatedInfo && html`
                    <div class="post-content preview">
                        <div class="truncated-title">Preview truncated.</div>
                        <div class="truncated-meta">
                            Showing first ${formatCountLabel(truncatedInfo.maxLength)} of ${formatCountLabel(truncatedInfo.originalLength)} chars. Download full text below.
                        </div>
                    </div>
                `}
                ${(fileRefs.length > 0 || messageRefs.length > 0 || attachmentPills.length > 0) && html`
                    <div class="post-file-refs">
                        ${messageRefs.map((id) => {
                            const scrollToRef = (e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                if (onScrollToMessage) {
                                    onScrollToMessage(id);
                                } else {
                                    const el = document.getElementById('post-' + id);
                                    if (el) {
                                        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                        el.classList.add('post-highlight');
                                        setTimeout(() => el.classList.remove('post-highlight'), 2000);
                                    }
                                }
                            };
                            return html`
                                <a href=${`#msg-${id}`} class="post-msg-pill-link" onClick=${scrollToRef}>
                                    <span class="post-file-pill" title=${'Message ' + id} onClick=${scrollToRef}>
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                                        </svg>
                                        <span class="post-file-name">${'msg:' + id}</span>
                                    </span>
                                </a>
                            `;
                        })}
                        ${fileRefs.map((ref) => {
                            const label = ref.split('/').pop() || ref;
                            return html`
                                <span class="post-file-pill" title=${ref}>
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                        <polyline points="14 2 14 8 20 8"/>
                                    </svg>
                                    <span class="post-file-name">${label}</span>
                                </span>
                            `;
                        })}
                        ${attachmentPills.map((attachment) => html`
                            <span class="post-file-pill" title=${attachment.label}
                                onClick=${onOpenAttachmentPreview ? (e) => { e.stopPropagation(); onOpenAttachmentPreview(attachment); } : undefined}
                                style=${onOpenAttachmentPreview ? { cursor: 'pointer' } : undefined}
                            >
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                    <polyline points="14 2 14 8 20 8"/>
                                </svg>
                                <span class="post-file-name">${attachment.label}</span>
                            </span>
                        `)}
                    </div>
                `}
                ${shouldRenderContent && html`
                    <div
                        ref=${contentRef}
                        class="post-content"
                        dangerouslySetInnerHTML=${{ __html: (() => {
                            const rendered = renderMarkdown ? renderMarkdown(displayContent, onHashtagClick) : displayContent;
                            const q = typeof highlightQuery === 'string' ? highlightQuery.trim() : '';
                            return q ? highlightHtml(rendered, q) : rendered;
                        })() }}
                        onClick=${(e) => {
                            if (e.target.classList.contains('hashtag')) {
                                e.preventDefault();
                                e.stopPropagation();
                                const tag = e.target.dataset.hashtag;
                                if (tag) onHashtagClick?.(tag);
                            } else if (e.target.tagName === 'IMG') {
                                e.preventDefault();
                                e.stopPropagation();
                                setZoomedImage(e.target.src);
                            }
                        }}
                    />
                `}
                ${textAnnotations.length > 0 && html`
                    ${textAnnotations.map((annotations, idx) => html`
                        <${AnnotationsBadge} key=${idx} annotations=${annotations} />
                    `)}
                `}
                ${filteredImageItems.length > 0 && html`
                    <div class="media-preview">
                        ${filteredImageItems.map(({ id }) => html`
                            <img
                                key=${id}
                                src=${getThumbnailUrl(id)}
                                alt="Media"
                                loading="lazy"
                                onClick=${(e) => handleImageClick(e, id)}
                            />
                        `)}
                    </div>
                `}
                ${filteredImageItems.length > 0 && html`
                    ${filteredImageItems.map(({ annotations }, idx) => html`
                        ${annotations && html`<${AnnotationsBadge} key=${idx} annotations=${annotations} />`}
                    `)}
                `}
                ${filteredFileIds.length > 0 && html`
                    <div class="file-attachments">
                        ${filteredFileIds.map((id) => html`
                            <${FileAttachment} key=${id} mediaId=${id} />
                        `)}
                    </div>
                `}
                ${resourceLinks.length > 0 && html`
                    <div class="resource-links">
                        ${resourceLinks.map((block, idx) => html`
                            <div key=${idx}>
                                <${ResourceLinkBlock} block=${block} />
                                <${AnnotationsBadge} annotations=${block.annotations} />
                            </div>
                        `)}
                    </div>
                `}
                ${resources.length > 0 && html`
                    <div class="resource-embeds">
                        ${resources.map((block, idx) => html`
                            <div key=${idx}>
                                <${ResourceBlock} block=${block} />
                                <${AnnotationsBadge} annotations=${block.annotations} />
                            </div>
                        `)}
                    </div>
                `}
                ${data.link_previews?.length > 0 && html`
                    <div class="link-previews">
                        ${data.link_previews.map((preview, i) => html`
                            <${LinkPreview} key=${i} preview=${preview} />
                        `)}
                    </div>
                `}
            </div>
        </div>
        ${zoomedImage && html`<${ImageModal} src=${zoomedImage} onClose=${() => setZoomedImage(null)} />`}
    `;
}

export function Timeline({
    posts,
    hasMore,
    onLoadMore,
    onPostClick,
    onHashtagClick,
    onMessageRef,
    onScrollToMessage,
    onOpenAttachmentPreview,
    emptyMessage,
    timelineRef,
    agents,
    user,
    onDeletePost,
    reverse = true,
    removingPostIds,
    searchQuery,
    renderMarkdown,
    renderMermaidDiagrams,
    getAgentName,
    getAgentAvatar,
    getAvatarInfo,
    formatTime,
    formatCount,
}) {
    const [loadingMore, setLoadingMore] = useState(false);
    const sentinelRef = useRef(null);
    const hasIntersectionObserver = typeof IntersectionObserver !== 'undefined';

    const triggerLoadMore = useCallback(async () => {
        if (!onLoadMore || !hasMore || loadingMore) return;
        setLoadingMore(true);
        try {
            await onLoadMore();
        } finally {
            setLoadingMore(false);
        }
    }, [hasMore, loadingMore, onLoadMore]);

    const handleScroll = useCallback((e) => {
        const { scrollTop, scrollHeight, clientHeight } = e.target;
        const distanceFromTop = reverse ? (scrollHeight - clientHeight - scrollTop) : scrollTop;
        const prefetchThreshold = Math.max(300, clientHeight);

        if (distanceFromTop < prefetchThreshold) {
            triggerLoadMore();
        }
    }, [reverse, triggerLoadMore]);

    useEffect(() => {
        if (!hasIntersectionObserver) return;
        if (!hasMore || !onLoadMore) return;
        const root = timelineRef?.current;
        const sentinel = sentinelRef.current;
        if (!root || !sentinel) return;

        const prefetchThreshold = Math.max(300, root.clientHeight || 0);
        const observer = new IntersectionObserver(
            (entries) => {
                if (entries.some((entry) => entry.isIntersecting)) {
                    triggerLoadMore();
                }
            },
            {
                root,
                rootMargin: `${prefetchThreshold}px 0px ${prefetchThreshold}px 0px`,
                threshold: 0,
            }
        );

        observer.observe(sentinel);
        return () => observer.disconnect();
    }, [hasIntersectionObserver, hasMore, onLoadMore, timelineRef, triggerLoadMore]);

    useEffect(() => {
        if (hasIntersectionObserver) return;
        if (!timelineRef?.current) return;
        const { scrollTop, scrollHeight, clientHeight } = timelineRef.current;
        const distanceFromTop = reverse ? (scrollHeight - clientHeight - scrollTop) : scrollTop;
        const prefetchThreshold = Math.max(300, clientHeight);

        if (distanceFromTop < prefetchThreshold) {
            triggerLoadMore();
        }
    }, [hasIntersectionObserver, posts, hasMore, reverse, timelineRef, triggerLoadMore]);

    if (!posts) {
        return html`<div class="loading"><div class="spinner"></div></div>`;
    }

    if (posts.length === 0) {
        return html`
            <div class="timeline" ref=${timelineRef}>
                <div class="timeline-content">
                    <div style="padding: var(--spacing-xl); text-align: center; color: var(--text-secondary)">
                        ${emptyMessage || 'No messages yet. Start a conversation!'}
                    </div>
                </div>
            </div>
        `;
    }

    const displayPosts = posts.slice().sort((a, b) => a.id - b.id);

    return html`
        <div class="timeline ${reverse ? 'reverse' : 'normal'}" ref=${timelineRef} onScroll=${hasIntersectionObserver ? undefined : handleScroll}>
            <div class="timeline-content">
                <div class="timeline-sentinel" ref=${sentinelRef}></div>
                ${displayPosts.map((post) => {
                    const isThreadReply = Boolean(post.data?.thread_id && post.data.thread_id !== post.id);
                    return html`
                    <${Post}
                        key=${post.id}
                        post=${post}
                        agentName=${getAgentName ? getAgentName(post.data?.agent_id, agents) : 'Agent'}
                        agentAvatarUrl=${getAgentAvatar ? getAgentAvatar(post.data?.agent_id, agents) : null}
                        userName=${user?.name || user?.user_name}
                        userAvatarUrl=${user?.avatar_url || user?.avatarUrl || user?.avatar}
                        isThreadReply=${isThreadReply}
                        isRemoving=${removingPostIds?.has(post.id)}
                        highlightQuery=${searchQuery}
                        onClick=${() => onPostClick?.(post)}
                        onHashtagClick=${onHashtagClick}
                        onMessageRef=${onMessageRef}
                        onScrollToMessage=${onScrollToMessage}
                        onDelete=${onDeletePost}
                        onOpenAttachmentPreview=${onOpenAttachmentPreview}
                        renderMarkdown=${renderMarkdown}
                        renderMermaidDiagrams=${renderMermaidDiagrams}
                        getAvatarInfo=${getAvatarInfo}
                        formatTime=${formatTime}
                        formatCount=${formatCount}
                    />
                `})}
            </div>
        </div>
    `;
}
