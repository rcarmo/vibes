const form = document.querySelector('#inspection');
const session = document.querySelector('#session');
const state = document.querySelector('#state');
const result = document.querySelector('#result');
let generation = 0;
let controller;
session.value = new URLSearchParams(location.search).get('session_id') || '';
session.addEventListener('input', () => {
    generation++;
    controller?.abort();
    result.textContent = '';
    state.textContent = 'Chat changed. Refresh to inspect.';
});
form.addEventListener('submit', async event => {
    event.preventDefault();
    const chat = session.value.trim();
    if (!chat) return;
    const request = ++generation;
    controller?.abort();
    controller = new AbortController();
    result.textContent = '';
    state.textContent = 'Inspecting…';
    try {
        const response = await fetch(`/diagnostics/backend?session_id=${encodeURIComponent(chat)}`, {
            cache: 'no-store', signal: controller.signal,
        });
        if (!response.ok) throw new Error('Inspection unavailable');
        const data = await response.json();
        if (request !== generation || chat !== session.value.trim()) return;
        if (!data || data.session_id !== chat) throw new Error('Inspection identity mismatch');
        result.textContent = JSON.stringify(data, null, 2);
        state.textContent = 'Snapshot received. Execution remains unverified.';
    } catch (error) {
        if (request !== generation || error.name === 'AbortError') return;
        state.textContent = 'Inspection unavailable. Check the chat ID and try again.';
    }
});
