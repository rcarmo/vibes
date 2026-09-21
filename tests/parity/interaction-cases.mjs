// Machine-readable index; executable flows are host-neutral modules added per slice.
export const interactionCases = Object.freeze([
  define('shell.workspace', ['workspace'], ['pointer', 'keyboard'], ['menu-open', 'focus-usable', 'workspace-open', 'composer-preserved', 'session-preserved']),
  define('quick-actions.typeahead', ['quickActions'], ['typing', 'keyboard', 'pointer', 'ime'], ['single-open', 'typed-query-preserved', 'grouped-results', 'focus-safe', 'draft-preserved', 'stale-result-rejected']),
  define('plan.roundtrip', ['planSidebar', 'planTool'], ['pointer', 'keyboard', 'tool'], ['revision-advanced', 'sse-scoped', 'dirty-preserved', 'conflict-retained', 'composer-preserved', 'session-isolated']),
  define('session.picker', ['sessions'], ['pointer', 'keyboard', 'ime'], ['selection-atomic', 'focus-restored', 'draft-scoped', 'late-response-rejected']),
  define('queue.lifecycle', ['queue'], ['pointer', 'keyboard', 'failure'], ['fifo', 'identity-scoped', 'failed-input-retained', 'return-before-delete', 'idempotent']),
  define('turn.cancel-reconnect', ['activity', 'cancel'], ['pointer', 'disconnect'], ['owner-scoped', 'busy-survives-disconnect', 'draft-preserved', 'stale-terminal-rejected']),
  define('attachments.copy-speech', ['attachments'], ['pointer', 'clipboard', 'speech'], ['single-delivery', 'cancel-retains-input', 'markdown-copy', 'playback-owned']),
]);
function define(id, requires, variants, outcomes) {
  return Object.freeze({ id, requires: Object.freeze(requires), variants: Object.freeze(variants), outcomes: Object.freeze(outcomes) });
}
export function interactionCase(id) {
  const found = interactionCases.find(item => item.id === id);
  if (!found) throw new Error('Unknown interaction case: ' + id);
  return found;
}
