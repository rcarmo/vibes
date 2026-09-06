const KEY = 'vibes_model_pins';
export function modelPinStorage(host = globalThis) {
    try { return host.localStorage; } catch { return null; }
}
export function loadModelPins(storage) {
    try {
        const value = JSON.parse(storage.getItem(KEY) || '[]');
        return Array.isArray(value) ? [...new Set(value.filter(item => typeof item === 'string' && item.length > 0 && item.length <= 1025))].slice(0, 100) : [];
    } catch { return []; }
}
export function saveModelPins(storage, pins) {
    try { storage.setItem(KEY, JSON.stringify(pins.slice(0, 100))); return true; }
    catch { return false; }
}
