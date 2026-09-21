import {test,expect} from 'bun:test';
import {interactionCases,interactionCase} from './interaction-cases.mjs';
test('interaction cases have unique concrete outcomes and immutable capability gates',()=>{
 expect(new Set(interactionCases.map(item=>item.id)).size).toBe(interactionCases.length);
 for(const item of interactionCases){
  expect(item.requires.length).toBeGreaterThan(0);
  expect(item.variants.length).toBeGreaterThan(0);
  expect(item.outcomes.length).toBeGreaterThan(1);
  expect(Object.isFrozen(item)).toBe(true);
 }
 expect(interactionCase('plan.roundtrip').requires).toEqual(['planSidebar','planTool']);
 expect(()=>interactionCase('invented')).toThrow();
});
