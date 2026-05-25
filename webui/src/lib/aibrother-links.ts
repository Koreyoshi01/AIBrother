import type { AIBrotherDocument } from "@/lib/types";

export const AIBROTHER_OPEN_FILE_EVENT = "aibrother:open-file";

export interface AIBrotherOpenFileDetail {
  path: string;
}

const MARKDOWN_PATH_RE = /(.+?\.md)(?::\d+)?(?:[#?].*)?$/i;
const URL_SCHEME_RE = /^[a-z][a-z0-9+.-]*:/i;

export function normalizeAIBrotherKnowledgePath(raw: string): string | null {
  let value = raw.trim();
  if (!value) return null;
  if (value.startsWith("#")) return null;

  value = value.replace(/^file:\/+/i, "");
  try {
    value = decodeURIComponent(value);
  } catch {
    // Keep the original value if it is not URL-encoded text.
  }

  value = value
    .replace(/\\/g, "/")
    .replace(/^["'(<\s]+|[)"'>\s]+$/g, "")
    .replace(/^\.?\//, "");

  const knowledgeIndex = value.toLowerCase().lastIndexOf("knowledge/");
  if (knowledgeIndex < 0 && URL_SCHEME_RE.test(value)) {
    return null;
  }

  const markdownMatch = MARKDOWN_PATH_RE.exec(value);
  if (!markdownMatch) return null;
  value = markdownMatch[1].replace(/^\.?\//, "");

  const normalizedKnowledgeIndex = value.toLowerCase().lastIndexOf("knowledge/");
  if (normalizedKnowledgeIndex >= 0) {
    return value.slice(normalizedKnowledgeIndex);
  }

  const aibrotherPrefix = "aibrother/";
  if (value.toLowerCase().startsWith(aibrotherPrefix)) {
    return value.slice(aibrotherPrefix.length);
  }

  return value.split("/").pop() ?? null;
}

export function getAIBrotherKnowledgePathFromLink(
  href: unknown,
): string | null {
  if (typeof href !== "string") return null;
  return normalizeAIBrotherKnowledgePath(href);
}

export function dispatchAIBrotherOpenFile(path: string): void {
  window.dispatchEvent(
    new CustomEvent<AIBrotherOpenFileDetail>(AIBROTHER_OPEN_FILE_EVENT, {
      detail: { path },
    }),
  );
}

export function resolveAIBrotherDocumentPath(
  documents: AIBrotherDocument[],
  requestedPath: string,
): string | null {
  const normalized = normalizeAIBrotherKnowledgePath(requestedPath);
  if (!normalized) return null;

  const normalizedLower = normalized.toLowerCase();
  const exact = documents.find((doc) => doc.path.toLowerCase() === normalizedLower);
  if (exact) return exact.path;

  const basename = normalizedLower.split("/").pop();
  if (!basename) return null;
  const byName = documents.find((doc) => doc.path.toLowerCase().split("/").pop() === basename);
  return byName?.path ?? null;
}
