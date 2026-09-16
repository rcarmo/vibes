import { test, expect } from 'bun:test';
import { PNG } from 'pngjs';
import { compare, overlay, unionRegion } from '../visual-parity/images.mjs';
import { state, scenarios } from '../visual-parity/state.mjs';
import { apiResponse, events, fixturePosts } from '../visual-parity/adapters.mjs';

test('dual UI fixture maps equivalent messages, model, metrics and scoped turn state', () => {
  for(const scenario of scenarios)for(const app of ['piclaw','vibes']) {
    expect(apiResponse(app,'/timeline',scenario).posts).toEqual(fixturePosts(scenario));
    expect(apiResponse(app,'/agent/context',scenario).tokens).toBe(state.context.tokens);
    expect(apiResponse(app,app==='piclaw'?'/agent/system-metrics':'/system/metrics',scenario).cpu_percent).toBe(25);
    expect(events(app,scenario)[0][1].thinking_level).toBe('medium');
  }
  expect(apiResponse('piclaw','/agent/status','working').active).toBe(true);
  expect(apiResponse('vibes','/agents/status','working').active_turns[0].turn_id).toBe('fixture-turn');
  expect(apiResponse('piclaw','/agent/queue-state','working').items[0].content).toBe(state.queue);
  expect(apiResponse('vibes','/agent/queue','working').items[0].content).toBe(state.queue);
  expect(apiResponse('vibes','/sessions/default/plan','idle')).toEqual({ markdown: '', revision: 0, updated_at: null });
  expect(apiResponse('piclaw','/unhandled','idle')).toBeUndefined();
});

test('pixel comparisons report identity and changed pixels without translation', () => {
  const a=new PNG({width:10,height:10});a.data.fill(255);
  const b=PNG.sync.read(PNG.sync.write(a));expect(compare(a,b).count).toBe(0);
  for(let y=2;y<8;y++)for(let x=2;x<8;x++){const i=(y*10+x)*4;b.data[i]=0;b.data[i+1]=0;b.data[i+2]=0;}
  expect(compare(a,b).count).toBe(36);
  expect(overlay(a,b).data[(3*10+3)*4]).toBe(128);
  const region=unionRegion(a,b,'.compose',[{'.compose':[{x:0,y:0,width:6,height:6}]},{'.compose':[{x:2,y:2,width:6,height:6}]}]);
  expect(region.rect).toEqual({x:0,y:0,width:8,height:8});
  expect(region.count).toBe(36);
  expect(()=>compare(a,new PNG({width:1,height:1}))).toThrow();
});
