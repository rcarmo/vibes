# Operator-selected workspace notes

Vibes can append selected Markdown notes to the startup prompt for Pi, ACP and Copilot FFI. Memory loading is disabled by default.

Add workspace-relative paths to `.vibes/settings.json`:

```json
{
  "memory_paths": ["notes/index.md", "notes/project.md"]
}
```

Restart Vibes after changing this list. Existing native sessions may retain their previous system prompt; create a new conversation when changing its initial context.

The loader accepts at most 16 distinct paths and 24,000 bytes in total. It accepts complete UTF-8 Markdown files confined to the current workspace. Absolute paths, traversal outside the workspace and symlinks resolving outside it are rejected. Missing, oversized and invalid-UTF-8 notes are omitted with diagnostics. Files are never modified.

Each included note carries its relative source path. The prompt labels note contents as reference data. Instructions inside a note do not grant tool permissions, change chat scope or override operator policy. Model adherence to that boundary still requires evaluation; the loader itself performs no commands.

`GET /diagnostics/backend` reports selected source paths and loading diagnostics without returning note text. It reports configured resources separately from verified execution. Use this endpoint only through the same trusted local/private-network access as the rest of Vibes.

Memory notes supplement native conversation history and compaction. The loader does not import PiClaw production state, credentials or another workspace, and does not automatically discover or write notes.
