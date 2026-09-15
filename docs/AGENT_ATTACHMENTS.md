# Agent image and file attachments

Agents can attach workspace files directly to timeline messages. The file is
stored in Vibes' media database and posted as an assistant-owned row during the
turn; the final answer does not have to repeat the image or contain base64.

## Tool entry points

* Pi: `vibes_attach_file`, provided by the bundled extension.
* ACP: `attach_file`, provided by the session's Vibes stdio MCP server. It is
  available even with message-history access disabled; the attachment-only server
  does not expose message or workspace-reading tools.
* ACP compatibility: `vibes/store_media_file` uses the same delivery path for
  agents that support that native request method.

The common arguments are `path`, optional `name`, `content_type` and `kind`
(`image` or `file`). Pi also accepts the earlier `mimeType` and `maxBytes`
parameters. Paths may be relative to the workspace or absolute within it.

For example, after creating `output/chart.png`, a Pi model calls:

```json
{"path":"output/chart.png","name":"chart.png","kind":"image"}
```

The tool returns a small receipt containing `media_id`, `message_id`, `name`,
`content_type`, `kind`, `size`, `url` and `reference` (for example `attachment:42`).
The image is already visible. To include it explicitly in a later message, the
model can use `![Chart](attachment:42)`. Numeric references resolve only against
media already referenced by messages in the same session. A bare reference does
not hide the image/download card. Arbitrary IDs are not matched to unrelated
attachments by position.

## Delivery and limits

Files are limited to 10 MiB and must be regular workspace files. Symlinks,
traversal and special files are rejected. Raster images are validated by content
and limited to 40 million pixels. PNG, JPEG, GIF, WebP and AVIF render inline;
SVG and other formats remain downloadable files. `kind: file` forces a download,
even for raster images. Vibes does not rasterise SVG automatically.

The local publishing endpoint is `POST /internal/agent-tools/attach-file`.
It requires an opaque capability supplied to the managed runtime, rejects browser
origins, and derives the destination from the active turn. Tool arguments cannot
choose another session. ACP capabilities are bound to their session; a changed
or ended turn cannot publish a delayed file into the next turn.

Pi tool-call IDs deduplicate retries within a turn. ACP callers can provide a
stable `request_id` when retrying; reusing it with different arguments is rejected.
There is a maximum of 100 distinct attachment receipts per turn. The persisted
row uses `intermediate: true` and arrives via `new_post`, not a final
`agent_response` event, so attaching does not clear the running status or Cancel
button. Media survives page reload independently of the source file and the
agent's eventual success, failure or cancellation.

The existing model-generated image/file blocks and Markdown data-URI handling
remain compatible, but the attachment tools are the preferred path. They keep
binary data out of model text and return a useful failure when delivery cannot
be completed.

## Differences from Piclaw

The common workspace-file-to-timeline workflow is supported through Pi and ACP,
including automatic cards, inline numeric references and download-only files.
Vibes does not provide Piclaw's SSH attachment pull-through or its separate
`read_attachment`/`export_attachment` tool APIs. Existing message tools provide
scoped metadata and text previews, not image input to every ACP provider. These
are distinct from sending an image to the user.

Validation: 570 backend tests, 28 frontend tests (161 assertions), and 150 focused
headed Chromium/WebKit tests passed with one worker and no retries. A real Pi
model invoked the bundled attachment tool once: the PNG appeared immediately,
remained after reload, and the final answer contained only a confirmation with
no media duplication. ACP native delivery, MCP HTTP delivery and attachment-only
stdio discovery have automated coverage; no live external ACP model call was
available for this check.
