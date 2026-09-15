import {test,expect} from 'bun:test';
import {normalizeSessionHandle} from '../../src/vibes/static/js/components/session-picker.js';
test('session display handles use Piclaw normalization without changing native IDs',()=>{
 expect(normalizeSessionHandle('Fixture session')).toBe('fixture-session');
 expect(normalizeSessionHandle('  Two   Spaces! ')).toBe('two-spaces');
 expect(normalizeSessionHandle('web:default')).toBe('web-default');
});
