import { useCallback, useEffect, useRef, useState } from '../vendor/preact-htm.js';

export const COMPOSE_HEIGHT_KEY = 'piclaw_compose_height';
export function composeLimits(width, height) {
    const min = width >= 1024 ? 70 : 50;
    return { min, auto: Math.max(min, Math.min(Math.floor(height * 0.4), 300)), max: Math.max(min, Math.min(Math.floor(height * 0.5), 520)) };
}
export function clampComposeHeight(value, width, height) {
    const { min, max } = composeLimits(width, height);
    return Math.max(min, Math.min(max, Math.round(Number(value) || min)));
}
function storedHeight() {
    try {
        const raw = localStorage.getItem(COMPOSE_HEIGHT_KEY);
        const n = Number(raw);
        return raw && Number.isFinite(n) && n > 0 ? n : null;
    } catch { return null; }
}

export function useComposeSizing(textareaRef, value) {
    const [initial] = useState(storedHeight);
    const manual = useRef(initial);
    const drag = useRef(null);
    const [height, setHeight] = useState(0);
    const resizeTextarea = useCallback(() => {
        const el = textareaRef.current;
        if (!el) return;
        const limits = composeLimits(innerWidth, innerHeight);
        el.style.minHeight = `${limits.min}px`;
        el.style.maxHeight = `${limits.max}px`;
        el.style.height = 'auto';
        const next = manual.current == null
            ? Math.max(limits.min, Math.min(el.scrollHeight, limits.auto))
            : clampComposeHeight(manual.current, innerWidth, innerHeight);
        // The local input-main is a flex column; retain the requested intrinsic height.
        el.style.minHeight = `${next}px`;
        el.style.height = `${next}px`;
        el.style.overflowY = el.scrollHeight > next ? 'auto' : 'hidden';
        setHeight(next);
        return next;
    }, [textareaRef]);
    const save = () => {
        if (manual.current == null) return;
        try { localStorage.setItem(COMPOSE_HEIGHT_KEY, String(manual.current)); } catch { /* Optional preference. */ }
    };
    const finish = useCallback(() => {
        const active = drag.current;
        if (!active) return;
        drag.current = null;
        document.body.style.cursor = active.cursor;
        document.body.style.userSelect = active.userSelect;
        active.handle.classList.remove('dragging');
        if (active.handle.hasPointerCapture(active.id)) active.handle.releasePointerCapture(active.id);
        save();
    }, []);
    useEffect(() => {
        resizeTextarea();
        window.addEventListener('resize', resizeTextarea);
        window.addEventListener('blur', finish);
        return () => { finish(); window.removeEventListener('resize', resizeTextarea); window.removeEventListener('blur', finish); };
    }, [resizeTextarea, finish]);
    useEffect(() => { resizeTextarea(); }, [value, resizeTextarea]);
    const limits = composeLimits(innerWidth, innerHeight);
    return {
        resizeTextarea,
        handleProps: {
            role: 'separator', tabIndex: 0, 'aria-orientation': 'horizontal',
            'aria-label': 'Resize input', title: 'Drag to resize input; use Arrow Up/Down to adjust',
            'aria-valuemin': limits.min, 'aria-valuemax': limits.max, 'aria-valuenow': height || limits.min,
            onPointerDown: event => {
                if (event.button !== 0 || !textareaRef.current || drag.current) return;
                event.preventDefault();
                const handle = event.currentTarget;
                handle.setPointerCapture(event.pointerId);
                drag.current = { id: event.pointerId, handle, y: event.clientY, height: textareaRef.current.getBoundingClientRect().height,
                    cursor: document.body.style.cursor, userSelect: document.body.style.userSelect };
                handle.classList.add('dragging');
                document.body.style.cursor = 'row-resize';
                document.body.style.userSelect = 'none';
            },
            onPointerMove: event => {
                if (drag.current?.id !== event.pointerId) return;
                manual.current = clampComposeHeight(drag.current.height + drag.current.y - event.clientY, innerWidth, innerHeight);
                resizeTextarea();
            },
            onPointerUp: finish, onPointerCancel: finish, onLostPointerCapture: finish,
            onKeyDown: event => {
                if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
                event.preventDefault();
                const current = textareaRef.current?.getBoundingClientRect().height || limits.min;
                manual.current = clampComposeHeight(event.key === 'Home' ? limits.min : event.key === 'End' ? limits.max : current + (event.key === 'ArrowUp' ? 20 : -20), innerWidth, innerHeight);
                resizeTextarea();
                save();
            },
        },
    };
}
