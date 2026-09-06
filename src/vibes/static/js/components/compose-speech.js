// Recognition owns no uploads; disposal invalidates callbacks before aborting.
export function speechInputConstructor(host = globalThis) {
    return host.isSecureContext ? (host.SpeechRecognition || host.webkitSpeechRecognition || null) : null;
}

export function shouldStartSpeechPushToTalk(event, value, { searchMode, available, active } = {}) {
    return (event.key === ' ' || event.key === 'Spacebar' || event.code === 'Space')
        && !event.ctrlKey && !event.metaKey && !event.altKey && !event.repeat
        && !searchMode && available && !active && !String(value || '').trim();
}

export function createSpeechInput(Recognition, { onText, onState, base = '' }) {
    const recognition = new Recognition();
    let disposed = false;
    let failed = false;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onstart = () => { if (!disposed) onState('listening'); };
    recognition.onresult = event => {
        if (disposed || failed) return;
        // Results are cumulative; rebuild rather than append duplicate interim text.
        const transcript = Array.from(event.results, result => result[0]?.transcript || '').join(' ').trim();
        onText([base.trimEnd(), transcript].filter(Boolean).join(' '));
    };
    recognition.onerror = event => {
        if (disposed) return;
        failed = true;
        const messages = {
            'not-allowed': 'Microphone permission denied.',
            'service-not-allowed': 'Speech recognition service unavailable.',
            'audio-capture': 'No microphone available.',
            'network': 'Speech recognition network error.',
            'no-speech': 'No speech detected.',
        };
        onState('error', messages[event.error] || 'Speech recognition failed.');
    };
    recognition.onend = () => { if (!disposed && !failed) onState('idle'); };
    return {
        start() {
            if (disposed) return;
            onState('requesting_permission');
            try { recognition.start(); }
            catch { failed = true; onState('error', 'Unable to start speech recognition.'); }
        },
        stop() { if (!disposed) { try { recognition.stop(); } catch { /* already stopped */ } } },
        dispose() {
            disposed = true;
            recognition.onstart = recognition.onresult = recognition.onerror = recognition.onend = null;
            try { recognition.abort(); } catch { /* already stopped */ }
        },
    };
}
