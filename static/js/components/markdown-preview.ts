import { html, useEffect, useRef, useState } from '../vendor/preact-htm.js';

const DEFAULT_HEIGHT = 220;
const MIN_HEIGHT = 60;
const STORAGE_KEY = 'vibes_md_preview_height';

type RenderMarkdown = (content: string) => string;
type RenderMermaidDiagrams = (root: HTMLElement) => Promise<unknown> | void;

export interface MarkdownPreviewProps {
    content?: string | null;
    onClose?: () => void;
    renderMarkdown?: RenderMarkdown;
    renderMermaidDiagrams?: RenderMermaidDiagrams;
}

interface ResizeSession {
    apply(clientY: number): void;
    finish(): void;
}

function getStoredHeight(): number {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        const value = raw ? Number(raw) : NaN;
        return Number.isFinite(value) && value >= MIN_HEIGHT ? value : DEFAULT_HEIGHT;
    } catch {
        return DEFAULT_HEIGHT;
    }
}

export function MarkdownPreview({ content, onClose, renderMarkdown, renderMermaidDiagrams }: MarkdownPreviewProps) {
    const [height, setHeight] = useState(getStoredHeight);
    const panelRef = useRef(null);
    const previewRef = useRef(null);

    useEffect(() => {
        const previewEl = previewRef.current as HTMLElement | null;
        if (!previewEl) return;
        previewEl.innerHTML = renderMarkdown ? renderMarkdown(content || '') : '';
        Promise.resolve(renderMermaidDiagrams?.(previewEl)).catch(() => {});
    }, [content, renderMarkdown, renderMermaidDiagrams]);

    const beginResize = (originY: number, splitter: HTMLElement): ResizeSession => {
        const panelEl = panelRef.current as HTMLElement | null;
        const startHeight = panelEl?.offsetHeight || height;
        const container = panelEl?.parentElement;
        const maxHeight = container ? container.offsetHeight * 0.7 : 500;
        splitter.classList.add('dragging');
        document.body.style.cursor = 'row-resize';
        document.body.style.userSelect = 'none';

        const apply = (clientY: number) => {
            const nextHeight = Math.min(Math.max(startHeight - (clientY - originY), MIN_HEIGHT), maxHeight);
            setHeight(nextHeight);
        };

        const finish = () => {
            splitter.classList.remove('dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            try {
                const panelEl = panelRef.current as HTMLElement | null;
                localStorage.setItem(STORAGE_KEY, String(Math.round(panelEl?.offsetHeight || height)));
            } catch {
                // ignore
            }
        };

        return { apply, finish };
    };

    const handleMouseDown = (event: MouseEvent) => {
        event.preventDefault();
        const resize = beginResize(event.clientY, event.currentTarget as HTMLElement);
        const onMove = (moveEvent: MouseEvent) => resize.apply(moveEvent.clientY);
        const onUp = () => {
            resize.finish();
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    };

    const handleTouchStart = (event: TouchEvent) => {
        event.preventDefault();
        const touch = event.touches[0];
        if (!touch) return;
        const resize = beginResize(touch.clientY, event.currentTarget as HTMLElement);
        const onMove = (moveEvent: TouchEvent) => {
            const nextTouch = moveEvent.touches[0];
            if (!nextTouch) return;
            moveEvent.preventDefault();
            resize.apply(nextTouch.clientY);
        };
        const onUp = () => {
            resize.finish();
            document.removeEventListener('touchmove', onMove);
            document.removeEventListener('touchend', onUp);
            document.removeEventListener('touchcancel', onUp);
        };
        document.addEventListener('touchmove', onMove, { passive: false });
        document.addEventListener('touchend', onUp);
        document.addEventListener('touchcancel', onUp);
    };

    return html`
        <div class="md-preview-splitter" onMouseDown=${handleMouseDown} onTouchStart=${handleTouchStart}></div>
        <div class="md-preview-panel" ref=${panelRef} style=${{ height: `${height}px` }}>
            <div class="md-preview-header">
                <span class="md-preview-title">Preview</span>
                <button class="md-preview-close" onClick=${onClose} title="Close preview" aria-label="Close preview">
                    <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
                        <line x1="4" y1="4" x2="12" y2="12" />
                        <line x1="12" y1="4" x2="4" y2="12" />
                    </svg>
                </button>
            </div>
            <div class="md-preview-body post-content" ref=${previewRef}></div>
        </div>
    `;
}
