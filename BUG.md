# Bug: Deletion events can skip timeline backfill due to stale SSE closure

## Summary

In the web frontend, the SSE `interaction_deleted` handler can run with stale values for `hasMore`, `currentHashtag`, `searchQuery`, and `loadMore`.  
When that happens, deleted items are removed from the visible timeline but the expected backfill (`loadMore`) may not run, leaving the conversation shorter than expected and breaking scrollback continuity.

## Affected code paths

- `piclaw/web/src/app.ts` (source)
- `piclaw/web/static/js/app.js` (built artifact)

Specifically, the SSE callback registered in the `useEffect` that creates `SSEClient` reads mutable UI state from closure-captured variables instead of current runtime values.

## Why it happens

The SSE subscription effect is not recreated for every relevant state transition, so callback logic may execute with old captured state.

Example problematic pattern (simplified):

```ts
if (eventType === "interaction_deleted") {
  setPosts(prev => prev ? prev.filter(p => !ids.includes(p.id)) : prev);
  if (hasMore && !currentHashtag && !searchQuery) {
    loadMore();
  }
}
```

If `hasMore/currentHashtag/searchQuery/loadMore` are stale in this closure, the condition can evaluate incorrectly and skip backfill.

## User-visible impact

- Timeline may lose messages after deletion without replenishing from older history.
- Scrollback appears inconsistent/incomplete after deletes.
- In some state transitions (search/hashtag/main timeline), behavior may be intermittent and hard to reproduce.

## Reproduction outline

1. Open timeline with enough history so `hasMore` is true.
2. Transition views (e.g., search mode or hashtag view) and return to main timeline.
3. Trigger deletion (local delete or SSE `interaction_deleted` event from another client/session).
4. Observe that deleted posts are removed but older posts are not always backfilled.

## Recommended fix

Use refs to read latest runtime state inside SSE callbacks:

- `viewStateRef` for `{ currentHashtag, searchQuery }`
- `hasMoreRef` for `hasMore`
- `loadMoreRef` for current `loadMore` function

Then in SSE handlers:

```ts
const { currentHashtag: activeHashtag, searchQuery: activeSearch } = viewStateRef.current;

if (eventType === "interaction_deleted") {
  setPosts(prev => prev ? prev.filter(p => !ids.includes(p.id)) : prev);
  if (hasMoreRef.current && !activeHashtag && !activeSearch) {
    loadMoreRef.current?.();
  }
}
```

Also apply the same current-state read for other timeline-gated SSE events (e.g., `new_post`, `agent_response`) to avoid stale view-mode checks.

## Validation

After patching, verify:

1. Deleting items on main timeline with `hasMore=true` consistently triggers backfill.
2. Search/hashtag views do not incorrectly backfill timeline state.
3. Cross-session delete events keep timeline length stable and scrollback continuous.

