import { createCaseState } from './canonical-state.mjs';
export const viewports = Object.freeze([
  { id: 'mobile', width: 390, height: 844 },
  { id: 'tablet', width: 820, height: 1180 },
  { id: 'desktop', width: 1440, height: 900 },
]);
export const legacyViewport = Object.freeze({ id: 'tablet-legacy', width: 1024, height: 768 });
export const themes = Object.freeze(['light', 'dark']);
export const engines = Object.freeze(['chromium', 'webkit']);
export const repeats = 2;
export const scenarios = Object.freeze([
  { id: 'idle', requires: ['planSidebar'] },
  { id: 'plan-open', requires: ['planSidebar'] },
  { id: 'populated', requires: ['planSidebar'] },
  { id: 'populated-plan-open', requires: ['planSidebar'] },
  { id: 'message-hover', requires: ['planSidebar', 'speechPlayback'] },
  { id: 'queued', requires: ['planSidebar', 'queue'] },
  { id: 'working', requires: ['planSidebar', 'activity', 'queue'] },
  { id: 'sessions', requires: ['planSidebar', 'sessions'] },
  { id: 'models', requires: ['planSidebar', 'models'] },
  { id: 'quick-actions', requires: ['planSidebar', 'quickActions'] },
  { id: 'workspace', requires: ['planSidebar', 'workspace'] },
]);
// The closed Plan toggle is visible, so even idle requires the sidebar capability.
// Plan tool is a separate behavioral gate; a screenshot cannot establish it.
export const behaviorContracts = Object.freeze([
  { id: 'plan-roundtrip', requires: ['planSidebar', 'planTool'], sequence: ['tool-write', 'sse-to-sidebar', 'sidebar-save', 'tool-read', 'stale-revision-rejected', 'other-session-unchanged'] },
]);
export function createCases(options = {}) {
  const chosenEngines = options.engines || engines, chosenThemes = options.themes || themes;
  const chosenViews = options.viewports || viewports;
  const chosenScenarios = options.scenarios || scenarios.map(item => item.id);
  const result = [];
  for (const engine of chosenEngines) for (const theme of chosenThemes) for (const view of chosenViews) for (const scenarioId of chosenScenarios) {
    if (!engines.includes(engine) || !themes.includes(theme)) throw new Error('Unknown canonical engine/theme');
    const scenario = scenarios.find(item => item.id === scenarioId);
    if (!scenario || !view.id || !Number.isInteger(view.width) || !Number.isInteger(view.height)) throw new Error('Invalid canonical case');
    result.push({ id: `${engine}-${theme}-${view.id}-${scenarioId}`, engine, theme, viewport: { width: view.width, height: view.height }, viewportId: view.id, scenario: scenarioId, requires: [...scenario.requires], repeats, state: createCaseState(scenarioId) });
  }
  return result;
}
