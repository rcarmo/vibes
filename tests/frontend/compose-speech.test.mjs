import { test, expect } from 'bun:test';
import { createSpeechInput, speechInputConstructor, shouldStartSpeechPushToTalk } from '../../src/vibes/static/js/components/compose-speech.js';

class Recognition {
    static latest;
    constructor() { Recognition.latest = this; }
    start() { this.started = true; }
    stop() { this.stopped = true; }
    abort() { this.aborted = true; }
}

test('speech support requires secure context and a recognition implementation', () => {
    expect(speechInputConstructor({ SpeechRecognition: Recognition })).toBe(null);
    expect(speechInputConstructor({ isSecureContext: true })).toBe(null);
    expect(speechInputConstructor({ isSecureContext: true, webkitSpeechRecognition: Recognition })).toBe(Recognition);
});

test('speech results replace interim text and disposal rejects late callbacks', () => {
    const texts = [], states = [];
    const input = createSpeechInput(Recognition, { base: 'Existing ', onText: text => texts.push(text), onState: state => states.push(state) });
    const recognition = Recognition.latest;
    input.start(); recognition.onstart();
    recognition.onresult({ results: [[{ transcript: 'hello' }]] });
    recognition.onresult({ results: [[{ transcript: 'hello world' }]] });
    expect(texts).toEqual(['Existing hello', 'Existing hello world']);
    expect(states).toEqual(['requesting_permission', 'listening']);
    input.stop(); expect(recognition.stopped).toBe(true);
    const late = recognition.onresult;
    input.dispose(); late({ results: [[{ transcript: 'stale' }]] });
    expect(texts).toHaveLength(2);
    expect(recognition.aborted).toBe(true);
    expect(recognition.onresult).toBe(null);
});

test('permission errors remain visible after recognition ends', () => {
    const states = [];
    createSpeechInput(Recognition, { onText() {}, onState: (...args) => states.push(args) }).start();
    Recognition.latest.onerror({ error: 'not-allowed' });
    Recognition.latest.onend();
    expect(states.at(-1)).toEqual(['error', 'Microphone permission denied.']);
});

test('push-to-talk starts only on unmodified space in an empty idle composer', () => {
    const options = { available: true, active: false };
    expect(shouldStartSpeechPushToTalk({ key: ' ' }, '', options)).toBe(true);
    for (const event of [{ key: ' ', repeat: true }, { key: ' ', ctrlKey: true }, { key: 'x' }]) {
        expect(shouldStartSpeechPushToTalk(event, '', options)).toBe(false);
    }
    expect(shouldStartSpeechPushToTalk({ key: ' ' }, 'draft', options)).toBe(false);
    expect(shouldStartSpeechPushToTalk({ key: ' ' }, '', { ...options, searchMode: true })).toBe(false);
});
