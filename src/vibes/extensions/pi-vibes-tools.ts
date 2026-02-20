import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Type } from "@sinclair/typebox";
import { readFile, stat } from "node:fs/promises";
import { basename, extname } from "node:path";

const MIME_MAP: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".svg": "image/svg+xml",
  ".pdf": "application/pdf",
  ".txt": "text/plain",
  ".md": "text/markdown",
  ".json": "application/json",
  ".csv": "text/csv",
};

function guessMime(path: string, override?: string): string {
  if (override) return override;
  const ext = extname(path).toLowerCase();
  return MIME_MAP[ext] ?? "application/octet-stream";
}

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "vibes_attach_file",
    label: "Vibes Attach File",
    description:
      "Attach a local file to the Vibes UI. Returns a file/image content block that Vibes will store and render.",
    parameters: Type.Object({
      path: Type.String({ description: "Path to file (relative or absolute)" }),
      name: Type.Optional(Type.String({ description: "Display name override" })),
      mimeType: Type.Optional(Type.String({ description: "MIME type override" })),
      maxBytes: Type.Optional(Type.Number({ description: "Max bytes to attach (default 10MB)" })),
    }),
    async execute(_toolCallId, params) {
      const maxBytes = params.maxBytes ?? 10 * 1024 * 1024;
      const filePath = params.path;
      const displayName = params.name ?? basename(filePath);
      const mimeType = guessMime(filePath, params.mimeType);

      const fileInfo = await stat(filePath);
      if (fileInfo.size > maxBytes) {
        return {
          content: [
            {
              type: "text",
              text: `File too large (${fileInfo.size} bytes > ${maxBytes}).`,
            },
          ],
        };
      }

      const data = await readFile(filePath);
      const encoded = data.toString("base64");

      const isImage = mimeType.startsWith("image/");
      const block = isImage
        ? {
            type: "image",
            data: encoded,
            mimeType,
            name: displayName,
            encoding: "base64",
          }
        : {
            type: "file",
            data: encoded,
            mimeType,
            name: displayName,
            encoding: "base64",
          };

      return {
        content: [
          {
            type: "text",
            text: `Attached ${displayName} (${mimeType}, ${fileInfo.size} bytes). Include the block in the final response.`,
          },
          block,
        ],
        details: {
          fileName: displayName,
          mimeType,
          size: fileInfo.size,
          vibesAttachment: {
            kind: isImage ? "image" : "file",
            name: displayName,
            mimeType,
            data: encoded,
            encoding: "base64",
          },
        },
      };
    },
  });
}
