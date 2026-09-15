import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Type } from "@sinclair/typebox";
export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "vibes_plan",
    label: "Session Plan",
    description: "Read or update the current session's persistent Plan sidebar. Actions read/write/update/patch/edit share the browser's revision-safe store. Read first; mutations require expected_revision from the latest read. Never choose a session. At most one item is in_progress; max 128 KiB. Patch indexes are 1-based; use index OR a unique match. Edit anchors must occur exactly once.",
    parameters: Type.Object({
      action: Type.String({ enum: ["read", "write", "update", "patch", "edit"] }),
      expected_revision: Type.Optional(Type.Integer({ minimum: 0 })),
      markdown: Type.Optional(Type.String()),
      plan: Type.Optional(Type.Array(Type.Object({ step: Type.String(), status: Type.String({ enum: ["pending", "in_progress", "completed"] }) }))),
      patches: Type.Optional(Type.Array(Type.Object({
        operation: Type.String({ enum: ["add", "update", "remove"] }),
        index: Type.Optional(Type.Integer({ minimum: 1 })), match: Type.Optional(Type.String()),
        step: Type.Optional(Type.String()), status: Type.Optional(Type.String({ enum: ["pending", "in_progress", "completed"] })),
        position: Type.Optional(Type.String({ enum: ["start", "end"] })),
      }))),
      edits: Type.Optional(Type.Array(Type.Object({
        operation: Type.Optional(Type.String({ enum: ["replace", "delete", "insert_before", "insert_after", "append", "prepend"] })),
        oldText: Type.Optional(Type.String()), newText: Type.Optional(Type.String()),
        anchorText: Type.Optional(Type.String()), text: Type.Optional(Type.String()),
      }))),
    }),
    async execute(_toolCallId, params, signal) {
      const base = process.env.VIBES_PI_TOOLS_URL;
      const token = process.env.VIBES_ATTACHMENT_TOKEN;
      if (!base || !token) throw new Error("Vibes Plan service is not configured");
      // Providers may materialise every optional property as an empty value.
      // Serialize only this action's schema fields; scope is never accepted here.
      const fields = { read: [], write: ['markdown'], update: ['plan'], patch: ['patches'], edit: ['edits'] };
      const allowed = new Set(['action', 'expected_revision', ...(fields[params.action] || [])]);
      const response = await fetch(new URL('/internal/agent-tools/plan', base), {
        method: 'POST', signal,
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
        body: JSON.stringify(Object.fromEntries(Object.entries(params).filter(([key, value]) => allowed.has(key) && value !== null && value !== undefined))),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Plan operation failed');
      return { content: [{ type: 'text', text: JSON.stringify(result) }], details: result };
    },
  });
  pi.registerTool({
    name: "vibes_messages",
    label: "Vibes Messages",
    description: "Retrieve referenced Vibes messages by row ID or search message text in the current Vibes session. Use this whenever the prompt contains a Messages section or msg:<id> reference.",
    parameters: Type.Object({
      action: Type.Union([Type.Literal("get"), Type.Literal("search")]),
      row_ids: Type.Optional(Type.Array(Type.Integer({ minimum: 1 }), { minItems: 1, maxItems: 50 })),
      query: Type.Optional(Type.String({ minLength: 1, maxLength: 500 })),
      limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 50 })),
      before_row: Type.Optional(Type.Integer({ minimum: 1 })),
    }),
    async execute(_toolCallId, params) {
      const base = process.env.VIBES_PI_TOOLS_URL;
      if (!base) return { content: [{ type: "text", text: "Vibes message access is not configured." }] };
      const response = await fetch(new URL("/internal/pi-tools/messages", base), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!response.ok) {
        return { content: [{ type: "text", text: `Vibes message access failed (${response.status}).` }] };
      }
      const result = await response.json();
      return { content: [{ type: "text", text: JSON.stringify(result) }], details: result };
    },
  });

  pi.registerTool({
    name: "vibes_attach_file",
    label: "Attach file to timeline",
    description: "Attach a workspace image or file (up to 10 MB) to the current chat. Stores and posts it immediately, returning a media ID and attachment: reference. Do not return base64 or copy the tool result into the final response. Raster images display inline; SVG and other files are downloads.",
    parameters: Type.Object({
      path: Type.String({ description: "Workspace-relative or absolute path inside the workspace" }),
      name: Type.Optional(Type.String()),
      content_type: Type.Optional(Type.String()),
      mimeType: Type.Optional(Type.String({ description: "Legacy alias for content_type" })),
      kind: Type.Optional(Type.String({ enum: ["image", "file"] })),
      maxBytes: Type.Optional(Type.Integer({ minimum: 1, maximum: 10485760 })),
    }),
    async execute(toolCallId, params, signal) {
      const base = process.env.VIBES_PI_TOOLS_URL;
      const token = process.env.VIBES_ATTACHMENT_TOKEN;
      if (!base || !token) throw new Error("Vibes attachment service is not configured");
      const { mimeType, maxBytes, ...fields } = params;
      const response = await fetch(new URL('/internal/agent-tools/attach-file', base), {
        method: "POST", signal,
        headers: { "Content-Type": "application/json", "Authorization": 'Bearer ' + token },
        body: JSON.stringify({ ...fields, content_type: fields.content_type || mimeType, max_bytes: maxBytes, request_id: toolCallId }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Attachment delivery failed");
      return { content: [{ type: "text", text: JSON.stringify(data) }], details: { attachment: data } };
    },
  });
}
