# Drafts, timestamps and permission review

The browser keeps streamed drafts separate from stored final messages. Drafts can change while tools run; only the persisted final response establishes completion.

## Draft streaming

Collapsed panels accept replacement preview snapshots and explicitly marked append chunks. Expanding a panel retrieves its full current text and consumes the dedicated delta stream. The browser does not consume both copies of a chunk. A missing or disconnected stream is not proof that the turn ended; session-scoped status polling restores known turn state.

## Message time

SQLite timestamps in `YYYY-MM-DD HH:MM:SS` form are UTC even though they omit a timezone suffix. The browser normalises that database format, preserves explicit ISO offsets, and displays relative ages. Labels refresh every 30 seconds. Hover over a message time for its absolute time in the browser's locale. These are server message timestamps; the browser clock still affects the displayed age.

## Reviewing a request

Permission requests show the proposed action, its description and available arguments. Native-shaped shell requests prioritise `fullCommandText`, show runtime warnings and working-directory/path hints, and keep the unmodified payload under **Technical details**. These hints come from the requesting backend and are not an independent safety verdict.

Commands wrap visually without changing or truncating their text. **Copy** copies the exact command, including line breaks; a browser selection fallback supports HTTP deployments without the Clipboard API. One vertically scrolling body keeps the action footer visible on narrow screens. The badge uses theme-aware contrast, and keyboard focus remains inside the dialog.

**Deny** and **Allow once** send the backend's original option IDs. Copying text, opening details, pressing Escape or clicking the backdrop does not approve a request. There is no implicit approval on opening the dialog. A timed-out, cancelled or already answered request may be rejected by the backend; the browser cannot revive it. Closing one request does not dismiss a newer request.

Some backends ask questions rather than permission. Choices and explicitly allowed free-form answers remain distinct from approval decisions. Browser support for a payload shape does not enable backend capabilities or install the Copilot SDK.

## Verification

Frontend unit tests cover timestamp parsing, append/snapshot handling, permission field extraction and SSE forwarding. Browser tests cover UTC/Lisbon/New York ages and refresh, expanded draft deduplication, exact copy, focus containment, and long commands at desktop/phone/landscape sizes. Speech and backend fixtures are synthetic; browser tests never approve a live request.
