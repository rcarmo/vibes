# Bounded widget sandbox browser probe

Headless Chromium rendered a widget published through the real Python widget
store/lookup routes using the candidate `0259e9a` FloatingWidgetPane and its actual
sandbox/message-source isolation patches. The interactive bridge accepted the
widget's own submit, rejected matching-key messages from the host and a sibling
iframe, denied parent DOM/storage access and blocked network fetch. A static
widget did not execute its script.

## Workload

Runtime `8ee472e`; disposable copied candidate files `floating-widget-pane.ts`,
`generated-widget-host-bridge.ts`, `generated-widget.ts` and
`patch-widget-isolation.mjs`. The exact candidate patch functions removed
`allow-same-origin` and required `event.source === iframe.contentWindow`.
The component was mounted with a thin Preact/HTM and translation shim using
Preact 10.29.2 and HTM 3.1.1; the complete Classic bundle was not built or changed.

The host created one isolated SQLite database and a captured synthetic Pi owner,
then called real `publish_widget` for interactive and static variants. After
publication it cleared ownership. The browser fetched the durable JSON artifact,
checked `application/json`, and confirmed a foreign-session lookup returned 404.
It mapped the artifact into the actual pane's existing descriptor fields. No
fake publication/lookup handler was used and no provider was called.

The interactive widget attempted parent DOM mutation, localStorage access and
fetch. Its own code reported all three denied through the real `piclawWidget.submit`
bridge, and the server recorded zero exfiltration requests. Host DOM remained
unchanged. The iframe sandbox allowed scripts/forms/downloads but omitted
same-origin. Host-origin and sibling opaque-frame messages carrying the correct
widget key did not invoke the pane callback. The static variant had only
`allow-downloads`; script/submit activity was absent. The successful interactive
page had no uncaught page errors. Expected CSP/sandbox denials were not application
exceptions.

Probe development initially used `activate` instead of the backend's `set_active`
helper and `type` instead of bridge `kind`. Inspection corrected these harness
API assumptions; the final fresh-database run passed, including the sibling-frame
check. These were harness failures, not diagnosed backend/sandbox defects.

The follow-up widget/race/message/SSE gate passed 25 tests in 1.51 seconds. No
backend source change was needed for the browser probe. The latest full regression
before this docs-only addition passed 1,085 tests with 13 existing skips.

## Limits and cleanup

This verifies the actual patched pane's browser isolation and callback boundary.
It does not verify complete-app timeline auto-open, refresh/runtime-state UI,
model follow-up admission, six-project widget acceptance, new tabs/popouts, media
permissions, all CSP resource types or Windows. The bridge callback deliberately
records submissions locally; it does not dispatch model work or pretend to do so.
The current consumer pin remains `4259e82`; no capability claims/skips or shared
frontend source were edited.

Host/browser, copied helper/component source, package dependencies, generated
bundle, synthetic database, probe scripts and disposable logs/test scratch are
removed after analysis. Only these concise conclusions remain. No provider,
deployment, repin, push or remote agent contact occurred.
