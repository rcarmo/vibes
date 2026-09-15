import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Type } from "@sinclair/typebox";
export default function (pi: ExtensionAPI) {
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
