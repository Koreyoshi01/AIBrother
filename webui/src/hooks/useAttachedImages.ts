import { useCallback, useEffect, useRef, useState } from "react";

import {
  encodeDocumentFile,
  MAX_ATTACHMENTS_PER_MESSAGE,
  resolveAttachmentKind,
  type AttachmentKind,
} from "@/lib/fileAttach";
import { encodeImage, type EncodeFailure } from "@/lib/imageEncode";
import type { KnowledgeImportResult } from "@/lib/nanobot-client";

/** Lifecycle stages of one attachment:
 *
 * - ``encoding``  — posted to the Worker; chip shows a spinner
 * - ``importing`` — encoded payload is being indexed into the knowledge base
 * - ``imported``  — stored in the knowledge base; safe to send text-only turns
 * - ``error``     — validation / decode / import failure; chip shows inline error
 */
export type AttachmentStatus = "encoding" | "importing" | "imported" | "error";

export interface AttachedImage {
  id: string;
  file: File;
  kind: AttachmentKind;
  /** Optimistic ``blob:`` preview URL for images; revoked on remove/clear. */
  previewUrl?: string;
  status: AttachmentStatus;
  /** Populated after encoding, before import completes. */
  dataUrl?: string;
  /** Size of the final encoded payload (base64 bytes decoded). */
  encodedBytes?: number;
  /** Whether the Worker re-encoded the image to hit the size budget. */
  normalized?: boolean;
  /** Knowledge-base path after a successful import. */
  knowledgePath?: string;
  /** Human-readable validation / encoding error when ``status === "error"``. */
  error?: AttachmentError;
}

/** Machine-readable rejection reasons surfaced as inline chip errors.
 *
 * Callers localize these via the ``composer.imageRejected.*`` i18n table. */
export type AttachmentError =
  | "unsupported_type"   // server whitelist excludes this MIME
  | "too_many_images"    // per-message cap reached before enqueue
  | "magic_mismatch"     // extension lies about the real content
  | "decode_failed"      // Worker couldn't decode / re-encode
  | "too_large"          // even after normalization we exceed the budget
  | "import_failed"      // knowledge-base import rejected by the server
  | "io";                // file read failed at the browser layer

export const MAX_IMAGES_PER_MESSAGE = MAX_ATTACHMENTS_PER_MESSAGE;

function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return (crypto as Crypto).randomUUID();
  }
  return `img-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function mapEncodeFailure(reason: EncodeFailure["reason"]): AttachmentError {
  switch (reason) {
    case "invalid_mime":
    case "magic_mismatch":
      return "magic_mismatch";
    case "too_large_after_normalize":
      return "too_large";
    case "io":
      return "io";
    case "decode_failed":
    default:
      return "decode_failed";
  }
}

export type KnowledgeImportFn = (
  dataUrl: string,
  file: File,
) => Promise<KnowledgeImportResult>;

export interface UseAttachedImagesApi {
  images: AttachedImage[];
  /** Enqueue new files. Returns the list of rejected files so the caller can
   * surface inline errors. Files rejected client-side (wrong MIME, limit) are
   * *not* added to ``images`` — only recoverable encoding failures show up as
   * error chips. */
  enqueue: (files: Iterable<File>) => {
    rejected: Array<{ file: File; reason: AttachmentError }>;
  };
  remove: (id: string) => { nextFocusId: string | null };
  /** Revoke every staged blob URL and drop all attachments. Called after a
   * successful submit — the optimistic bubble holds onto an independent
   * ``data:`` URL so tearing down blob previews here is safe. */
  clear: () => void;
  /** ``true`` when at least one attachment is still encoding — Send should wait. */
  encoding: boolean;
  /** ``true`` when at least one attachment is being imported into the KB. */
  importing: boolean;
  /** ``true`` when we've hit ``MAX_ATTACHMENTS_PER_MESSAGE``. */
  full: boolean;
}

/** Manage the lifecycle of images attached to the Composer.
 *
 * Responsibilities in one place:
 *   - validation (MIME whitelist, count cap)
 *   - blob URL creation + revocation
 *   - Worker orchestration
 *   - automatic knowledge-base import
 *   - focus bookkeeping so keyboard delete doesn't strand the user
 */
export function useAttachedImages(
  onKnowledgeImport?: KnowledgeImportFn,
): UseAttachedImagesApi {
  const [images, setImages] = useState<AttachedImage[]>([]);
  const importRef = useRef(onKnowledgeImport);
  importRef.current = onKnowledgeImport;

  // Ref mirror so ``enqueue`` can see the authoritative length when invoked
  // multiple times in a single tick (rapid file selection, drag of many
  // files, paste storms). ``state`` is stale for that second + call.
  const imagesRef = useRef<AttachedImage[]>([]);
  imagesRef.current = images;

  const setEntry = useCallback((id: string, patch: Partial<AttachedImage>) => {
    setImages((prev) => {
      const next = prev.map((img) => (img.id === id ? { ...img, ...patch } : img));
      imagesRef.current = next;
      return next;
    });
  }, []);

  const importEncoded = useCallback(
    (entryId: string, dataUrl: string, file: File) => {
      const importer = importRef.current;
      if (!importer) {
        setEntry(entryId, { status: "imported" });
        return;
      }
      setEntry(entryId, { status: "importing", dataUrl });
      void importer(dataUrl, file).then(
        (result) => {
          setEntry(entryId, {
            status: "imported",
            knowledgePath: result.path,
          });
        },
        () => {
          setEntry(entryId, {
            status: "error",
            error: "import_failed",
          });
        },
      );
    },
    [setEntry],
  );

  const enqueue = useCallback(
    (files: Iterable<File>) => {
      const rejected: Array<{ file: File; reason: AttachmentError }> = [];
      const toAdd: AttachedImage[] = [];
      let slot = MAX_ATTACHMENTS_PER_MESSAGE - imagesRef.current.length;

      for (const file of files) {
        const kind = resolveAttachmentKind(file);
        if (!kind) {
          rejected.push({ file, reason: "unsupported_type" });
          continue;
        }
        if (slot <= 0) {
          rejected.push({ file, reason: "too_many_images" });
          continue;
        }
        slot -= 1;
        toAdd.push({
          id: uuid(),
          file,
          kind,
          previewUrl: kind === "image" ? URL.createObjectURL(file) : undefined,
          status: "encoding",
        });
      }

      if (toAdd.length > 0) {
        const next = [...imagesRef.current, ...toAdd];
        imagesRef.current = next;
        setImages(next);
        // Fire encoding after the commit so chips render first (good INP).
        for (const entry of toAdd) {
          queueMicrotask(() => {
            if (entry.kind === "document") {
              void encodeDocumentFile(entry.file).then(
                (result) => {
                  if (result.ok) {
                    importEncoded(entry.id, result.dataUrl, entry.file);
                    setEntry(entry.id, {
                      encodedBytes: result.bytes,
                      normalized: false,
                    });
                  } else {
                    setEntry(entry.id, {
                      status: "error",
                      error: result.reason,
                    });
                  }
                },
                () => {
                  setEntry(entry.id, {
                    status: "error",
                    error: "io",
                  });
                },
              );
              return;
            }
            encodeImage(entry.file).then(
              (result) => {
                if (result.ok) {
                  importEncoded(entry.id, result.dataUrl, entry.file);
                  setEntry(entry.id, {
                    encodedBytes: result.bytes,
                    normalized: result.normalized,
                  });
                } else {
                  setEntry(entry.id, {
                    status: "error",
                    error: mapEncodeFailure(result.reason),
                  });
                }
              },
              () => {
                setEntry(entry.id, {
                  status: "error",
                  error: "decode_failed",
                });
              },
            );
          });
        }
      }
      return { rejected };
    },
    [importEncoded, setEntry],
  );

  const remove = useCallback((id: string) => {
    let nextFocusId: string | null = null;
    setImages((prev) => {
      const idx = prev.findIndex((img) => img.id === id);
      if (idx === -1) return prev;
      const target = prev[idx];
      if (target.previewUrl) {
        try {
          URL.revokeObjectURL(target.previewUrl);
        } catch {
          // No-op: previewUrl revocation is best-effort.
        }
      }
      const next = [...prev.slice(0, idx), ...prev.slice(idx + 1)];
      imagesRef.current = next;
      // Prefer moving focus to the chip at the same index, else previous.
      const candidate = next[idx] ?? next[idx - 1];
      nextFocusId = candidate?.id ?? null;
      return next;
    });
    return { nextFocusId };
  }, []);

  const clear = useCallback(() => {
    setImages((prev) => {
      for (const img of prev) {
        if (!img.previewUrl) continue;
        try {
          URL.revokeObjectURL(img.previewUrl);
        } catch {
          // revoke is best-effort
        }
      }
      imagesRef.current = [];
      return [];
    });
  }, []);

  // Final safety net: revoke any outstanding blob URLs on unmount. Safe
  // under StrictMode double-invoke because revoked blob URLs are only
  // referenced from in-hook chip state, which is rebuilt on remount.
  useEffect(() => {
    return () => {
      for (const img of imagesRef.current) {
        if (!img.previewUrl) continue;
        try {
          URL.revokeObjectURL(img.previewUrl);
        } catch {
          // best-effort cleanup on unmount
        }
      }
    };
  }, []);

  const encoding = images.some((img) => img.status === "encoding");
  const importing = images.some((img) => img.status === "importing");
  const full = images.length >= MAX_ATTACHMENTS_PER_MESSAGE;

  return { images, enqueue, remove, clear, encoding, importing, full };
}
