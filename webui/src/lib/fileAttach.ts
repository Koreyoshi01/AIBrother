/** Shared attachment rules for the WebUI composer (aligned with websocket ingress). */

export const MAX_ATTACHMENTS_PER_MESSAGE = 4;
export const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024;

export const IMAGE_MIMES: ReadonlySet<string> = new Set([
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/gif",
]);

export const DOCUMENT_MIMES: ReadonlySet<string> = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "text/plain",
]);

const EXTENSION_TO_MIME: Record<string, string> = {
  ".pdf": "application/pdf",
  ".docx":
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ".xlsx":
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ".pptx":
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  ".txt": "text/plain",
};

export type AttachmentKind = "image" | "document";

export function fileExtension(name: string): string {
  const base = name.split(/[?#]/, 1)[0]?.toLowerCase() ?? "";
  const idx = base.lastIndexOf(".");
  return idx >= 0 ? base.slice(idx) : "";
}

export function resolveAttachmentKind(file: File): AttachmentKind | null {
  if (IMAGE_MIMES.has(file.type)) return "image";
  if (DOCUMENT_MIMES.has(file.type)) return "document";
  const ext = fileExtension(file.name);
  if (ext in EXTENSION_TO_MIME) return "document";
  return null;
}

export function resolvedDocumentMime(file: File): string | null {
  if (DOCUMENT_MIMES.has(file.type)) return file.type;
  const ext = fileExtension(file.name);
  return EXTENSION_TO_MIME[ext] ?? null;
}

export function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") resolve(reader.result);
      else reject(new Error("read_failed"));
    };
    reader.onerror = () => reject(new Error("read_failed"));
    reader.readAsDataURL(file);
  });
}

export async function encodeDocumentFile(
  file: File,
): Promise<
  | { ok: true; dataUrl: string; bytes: number; mime: string }
  | { ok: false; reason: "unsupported_type" | "too_large" | "io" }
> {
  const mime = resolvedDocumentMime(file);
  if (!mime) return { ok: false, reason: "unsupported_type" };
  if (file.size > MAX_DOCUMENT_BYTES) return { ok: false, reason: "too_large" };
  try {
    const dataUrl = await readFileAsDataUrl(file);
    if (!dataUrl.startsWith(`data:${mime};base64,`)) {
      const comma = dataUrl.indexOf(",");
      if (comma < 0) return { ok: false, reason: "io" };
      const payload = dataUrl.slice(comma + 1);
      return {
        ok: true,
        dataUrl: `data:${mime};base64,${payload}`,
        bytes: file.size,
        mime,
      };
    }
    return { ok: true, dataUrl, bytes: file.size, mime };
  } catch {
    return { ok: false, reason: "io" };
  }
}

export const ACCEPT_ATTR =
  "image/png,image/jpeg,image/webp,image/gif,.pdf,.docx,.xlsx,.pptx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.openxmlformats-officedocument.presentationml.presentation,text/plain";
