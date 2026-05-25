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

/** Join a markdown-relative asset href against the document path inside ``knowledge/``. */
export function joinKnowledgeAssetPath(docPath: string, href: string): string {
  const docDir = docPath.replace(/\\/g, "/").replace(/\/[^/]+$/, "");
  const normalized = href.replace(/\\/g, "/").trim();
  if (normalized.toLowerCase().startsWith("knowledge/")) {
    return collapseKnowledgePath(normalized);
  }
  return collapseKnowledgePath(`${docDir}/${normalized}`);
}

function collapseKnowledgePath(path: string): string {
  const parts: string[] = [];
  for (const part of path.replace(/\\/g, "/").split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") {
      parts.pop();
      continue;
    }
    parts.push(part);
  }
  return parts.join("/");
}

export function aibrotherAssetUrl(
  assetPath: string,
  token: string,
  base: string = "",
): string {
  const query = new URLSearchParams();
  query.set("path", assetPath);
  query.set("token", token);
  return `${base}/api/aibrother/asset?${query.toString()}`;
}

const MARKDOWN_IMAGE_RE =
  /!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;

/** Rewrite relative ``![alt](assets/foo.png)`` links to authenticated API URLs. */
export function rewriteKnowledgeMarkdownAssets(
  content: string,
  docPath: string,
  token: string,
  base: string = "",
): string {
  return content.replace(MARKDOWN_IMAGE_RE, (full, alt: string, href: string) => {
    const trimmed = href.trim();
    if (/^(https?:|data:|\/api\/)/i.test(trimmed)) {
      return full;
    }
    const assetPath = joinKnowledgeAssetPath(docPath, trimmed);
    const url = aibrotherAssetUrl(assetPath, token, base);
    return `![${alt}](${url})`;
  });
}
