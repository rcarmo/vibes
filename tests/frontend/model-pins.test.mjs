import { test, expect } from 'bun:test';
import { loadModelPins, saveModelPins } from '../../src/vibes/static/js/components/model-pins.js';
test('model pins validate storage and tolerate denied writes', () => {
    let value = '["p/m",null,"p/m",12]';
    const storage = { getItem: () => value, setItem: (_, next) => { value = next; } };
    expect(loadModelPins(storage)).toEqual(['p/m']);
    expect(saveModelPins(storage, ['p/new'])).toBe(true);
    expect(loadModelPins(storage)).toEqual(['p/new']);
    expect(loadModelPins({ getItem() { throw Error(); } })).toEqual([]);
    expect(saveModelPins({ setItem() { throw Error(); } }, [])).toBe(false);
});

test('denied storage property access is safe for model pin callers', async () => {
    const { modelPinStorage } = await import('../../src/vibes/static/js/components/model-pins.js');
    const host = { get localStorage() { throw new Error('SecurityError'); } };
    expect(modelPinStorage(host)).toBe(null);
    expect(loadModelPins(modelPinStorage(host))).toEqual([]);
    expect(saveModelPins(modelPinStorage(host), ['p/m'])).toBe(false);
});
