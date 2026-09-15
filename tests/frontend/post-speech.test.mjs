import { test, expect } from 'bun:test';
import { buildSpeakablePostText, getSpeechPlaybackState, isSpeechSynthesisSupported, speakPostText, stopSpeechPlayback, subscribeSpeechPlayback } from '../../src/vibes/static/js/components/post-speech.js';

function runtime() {
    const spoken = [];
    let cancelled = 0;
    return { spoken, get cancelled() { return cancelled; }, window: {
        speechSynthesis: { cancel() { cancelled++; }, speak(utterance) { spoken.push(utterance); } },
        SpeechSynthesisUtterance: class { constructor(text) { this.text = text; } },
    } };
}
test('speech capability and bounded Markdown text', () => {
    expect(isSpeechSynthesisSupported({ window: {} })).toBe(false);
    expect(speakPostText('a', 'hello', { window: {} })).toBe(false);
    expect(isSpeechSynthesisSupported(runtime())).toBe(true);
    expect(buildSpeakablePostText('# Heading\n\n[link](https://example.invalid)\n```js\nsecret code\n```')).toBe('Heading. link Code block omitted.');
    expect(buildSpeakablePostText('x'.repeat(2000))).toHaveLength(1600);
    expect(buildSpeakablePostText(null)).toBe('');
});
test('speech transfers ownership, ignores old completion and resets on stop or failure', () => {
    const env = runtime(), states = [];
    const unsubscribe = subscribeSpeechPlayback(value => states.push(value));
    expect(speakPostText('one', 'First', env)).toBe(true);
    expect(speakPostText('two', 'Second', env)).toBe(true);
    env.spoken[0].onend();
    expect(getSpeechPlaybackState()).toEqual({ activePostId: 'two', speaking: true });
    env.spoken[1].onerror();
    expect(getSpeechPlaybackState().speaking).toBe(false);
    speakPostText('three', 'Third', env);
    stopSpeechPlayback(env);
    env.spoken[2].onend();
    expect(getSpeechPlaybackState()).toEqual({ activePostId: null, speaking: false });
    env.window.speechSynthesis.speak = () => { throw new Error('Fixture unavailable'); };
    expect(speakPostText('four', 'Fourth', env)).toBe(false);
    expect(states.at(-1).speaking).toBe(false);
    expect(env.cancelled).toBe(5);
    unsubscribe();
});
