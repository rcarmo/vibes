// Adapted from Piclaw classic 3.1.2 post-speech.ts. Copyright (c) 2026 Rui Carmo.
// MIT license: ../vendor/licenses/PICLAW-MIT.txt
// The host supplies raw stored Markdown and an opaque mounted-post owner key.

let activeToken = 0;
let activeUtterance = null;
let playbackState = {
    activePostId: null,
    speaking: false,
};
const listeners = new Set();

function getWindowRuntime(runtime = {}) {
    return runtime.window ?? (typeof window !== 'undefined' ? window : null);
}

function getSpeechSynthesis(runtime = {}) {
    const win = getWindowRuntime(runtime);
    return win?.speechSynthesis || null;
}

function emitPlaybackState() {
    const snapshot = { ...playbackState };
    for (const listener of listeners) {
        try {
            listener(snapshot);
        } catch (error) {
            console.warn('[post-speech] playback listener failed:', error);
        }
    }
}

export function getSpeechPlaybackState() {
    return { ...playbackState };
}

export function subscribeSpeechPlayback(listener) {
    if (typeof listener !== 'function') return () => {};
    listeners.add(listener);
    listener(getSpeechPlaybackState());
    return () => listeners.delete(listener);
}

export function isSpeechSynthesisSupported(runtime = {}) {
    const win = getWindowRuntime(runtime);
    return Boolean(win && win.speechSynthesis && typeof win.SpeechSynthesisUtterance === 'function');
}

export function buildSpeakablePostText(raw) {
    if (!raw) return '';

    return String(raw)
        .replace(/```[\s\S]*?```/g, ' Code block omitted. ')
        .replace(/`([^`]+)`/g, '$1')
        .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '$1')
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1')
        .replace(/^#{1,6}\s+/gm, '')
        .replace(/^>\s?/gm, '')
        .replace(/^[-*+]\s+/gm, '• ')
        .replace(/\n{3,}/g, '\n\n')
        .replace(/\n\n+/g, '. ')
        .replace(/\s+/g, ' ')
        .replace(/\s+([.,;:!?])/g, '$1')
        .trim()
        .slice(0, 1600);
}

export function stopSpeechPlayback(runtime = {}) {
    const synth = getSpeechSynthesis(runtime);
    activeToken += 1;
    activeUtterance = null;
    playbackState = {
        activePostId: null,
        speaking: false,
    };
    if (synth) {
        try {
            synth.cancel();
        } catch (error) {
            console.warn('[post-speech] cancel failed:', error);
        }
    }
    emitPlaybackState();
}

export function speakPostText(postId, text, runtime = {}) {
    const win = getWindowRuntime(runtime);
    const synth = getSpeechSynthesis(runtime);
    if (!win || !synth || typeof win.SpeechSynthesisUtterance !== 'function') return false;
    const speakable = String(text || '').trim();
    if (!speakable) return false;

    const token = activeToken + 1;
    activeToken = token;
    try {
        synth.cancel();
    } catch {
        /* noop */
    }

    const utterance = new win.SpeechSynthesisUtterance(speakable);
    activeUtterance = utterance;
    playbackState = {
        activePostId: postId,
        speaking: true,
    };
    emitPlaybackState();

    const finalize = () => {
        if (token !== activeToken) return;
        activeUtterance = null;
        playbackState = {
            activePostId: null,
            speaking: false,
        };
        emitPlaybackState();
    };

    utterance.onend = finalize;
    utterance.onerror = finalize;

    try {
        synth.speak(utterance);
        return true;
    } catch (error) {
        console.warn('[post-speech] speak failed:', error);
        finalize();
        return false;
    }
}
