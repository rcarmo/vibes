import {test,expect} from 'bun:test';
import {createCaseState} from '../canonical-state.mjs';
import {createVibesAdapter,vibesResponses,vibesSessionId} from './vibes.mjs';
test('Vibes native formats preserve canonical session/metrics/queue values',()=>{
 const state=createCaseState('working'),wire=vibesResponses(state);
 expect(vibesSessionId('main')).toBe('default');
 expect(wire['/sessions'].sessions[0].name).toBe('Fixture session');
 expect(wire['/timeline'].posts[0].data.session_id).toBe('default');
 expect(wire['/agent/queue'].items.map(i=>i.row_id)).toEqual([201,202]);
 expect(wire['/system/metrics'].process_memory.rss_bytes).toBe(104857600);
 expect(wire['/workspace/tree'].root.children).toHaveLength(state.workspace.entries.length);
 expect(wire['/agent/context'].used_tokens).toBe(16384);
});
test('persistent Plan maps the native revision contract after real tool/sidebar roundtrip verification',()=>{
 const adapter=createVibesAdapter();
 expect(adapter.capabilities.planSidebar).toBe(true);
 expect(adapter.capabilities.planTool).toBe(true);
 const wire=vibesResponses(createCaseState('plan-open'));
 expect(wire['/sessions/default/plan'].revision).toBe(1);
 expect(wire['/sessions/default/plan'].markdown).toContain('Verify tablet layout');
});
