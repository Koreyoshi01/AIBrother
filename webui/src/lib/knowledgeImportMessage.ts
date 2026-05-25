/** UI-facing knowledge import attachment (transcript replay + optimistic bubble). */
export type { UIKnowledgeImport } from "@/lib/types";

/** Reference to a file the user just imported into the group knowledge base. */
export interface KnowledgeImportRef {
  filename: string;
  path: string;
  title?: string;
  sizeBytes?: number;
  mimeType?: string;
}

/** Human-readable file kind label for attachment cards (PDF, DOCX, …). */
export function knowledgeImportKindLabel(
  filename: string,
  mimeType?: string,
): string {
  const mime = mimeType?.toLowerCase() ?? "";
  if (mime.includes("pdf")) return "PDF";
  if (mime.includes("word") || mime.includes("document")) return "DOCX";
  if (mime.includes("spreadsheet") || mime.includes("excel")) return "XLSX";
  if (mime.includes("presentation") || mime.includes("powerpoint")) return "PPTX";
  if (mime.startsWith("text/")) return "TXT";
  if (mime.startsWith("image/")) return "Image";

  const ext = filename.includes(".")
    ? filename.slice(filename.lastIndexOf(".") + 1).toLowerCase()
    : "";
  switch (ext) {
    case "pdf":
      return "PDF";
    case "docx":
      return "DOCX";
    case "xlsx":
      return "XLSX";
    case "pptx":
      return "PPTX";
    case "txt":
      return "TXT";
    case "png":
    case "jpg":
    case "jpeg":
    case "webp":
    case "gif":
      return "Image";
    default:
      return ext ? ext.toUpperCase() : "File";
  }
}

/** Wire payload shape for ``knowledge_imports`` on outbound WS frames. */
export function knowledgeImportsWirePayload(
  imports: KnowledgeImportRef[],
): Array<{
  filename: string;
  path: string;
  title?: string;
  size_bytes?: number;
  mime_type?: string;
}> {
  return imports.map((item) => ({
    filename: item.filename,
    path: item.path,
    ...(item.title ? { title: item.title } : {}),
    ...(item.sizeBytes != null ? { size_bytes: item.sizeBytes } : {}),
    ...(item.mimeType ? { mime_type: item.mimeType } : {}),
  }));
}
