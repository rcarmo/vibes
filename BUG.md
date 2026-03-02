# Bug: Draft deltas stream even when Draft panel is collapsed

## Summary

When the Draft panel is collapsed, piclaw still emits `agent_draft_delta` SSE events for every token.
The collapsed UI path does not consume those deltas, so this creates avoidable traffic and event churn.

Thought deltas are already gated by expansion state, so Draft/Thought behavior is inconsistent.

## Affected code

- `piclaw/src/channels/web/agent-events.ts`
- `piclaw/web/static/js/app.js` (or `web/src/app.ts`)

## Current behavior

- `agent_thought_delta` is sent only when `includeThoughtFull?.()` is true.
- `agent_draft_delta` is sent unconditionally on each `text_delta`.
- In collapsed Draft mode, frontend ignores deltas (`draftExpandedRef.current` check).

## Expected behavior

For both Draft and Thought:

1. **Collapsed**: preview stream only (`agent_draft` / `agent_thought`), no deltas.
2. **Expanded**: full streaming via `*_delta`.
3. **Collapsed again**: stop deltas and return to preview-only.

## Reproduction

1. Start a long response that streams many tokens.
2. Keep Draft collapsed.
3. Inspect `/sse/stream` in DevTools.
4. Observe continuous `agent_draft_delta` events while collapsed.

## Suggested fix

Gate draft delta emission in `agent-events.ts` similarly to thought:

```ts
if (messageEvent.type === "text_delta") {
  // emit preview
  options.emitter.draft({ ... });

  if (options.includeDraftFull?.()) {
    options.emitter.draftDelta({ ...base, delta: messageEvent.delta });
  }
}
```

Optionally add reset semantics on expand transitions, matching thought handling.
