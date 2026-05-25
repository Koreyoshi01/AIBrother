import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpen, RefreshCw } from "lucide-react";

import { MarkdownText } from "@/components/MarkdownText";
import { ThreadHeader } from "@/components/thread/ThreadHeader";
import { Button } from "@/components/ui/button";
import { useClient } from "@/providers/ClientProvider";
import {
  fetchAIBrotherFile,
  fetchAIBrotherKnowledge,
  reindexAIBrotherKnowledge,
} from "@/lib/api";
import { resolveAIBrotherDocumentPath } from "@/lib/aibrother-links";
import type { AIBrotherDocument, AIBrotherFile } from "@/lib/types";
import { cn } from "@/lib/utils";

interface AIBrotherViewProps {
  theme: "light" | "dark";
  onToggleTheme: () => void;
  onToggleSidebar: () => void;
  hideSidebarToggleOnDesktop?: boolean;
  openRequest?: { id: number; path: string } | null;
}

export function AIBrotherView({
  theme,
  onToggleTheme,
  onToggleSidebar,
  hideSidebarToggleOnDesktop = false,
  openRequest = null,
}: AIBrotherViewProps) {
  const { token } = useClient();
  const [documents, setDocuments] = useState<AIBrotherDocument[]>([]);
  const [selected, setSelected] = useState<AIBrotherFile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingOpenPath, setPendingOpenPath] = useState<string | null>(null);

  const grouped = useMemo(() => {
    const map = new Map<string, AIBrotherDocument[]>();
    documents.forEach((doc) => {
      const key = doc.category_label || doc.category;
      map.set(key, [...(map.get(key) ?? []), doc]);
    });
    return Array.from(map.entries());
  }, [documents]);

  const openFile = useCallback(
    async (path: string) => {
      setError(null);
      try {
        setSelected(await fetchAIBrotherFile(token, path));
      } catch (e) {
        setError((e as Error).message);
      }
    },
    [token],
  );

  const loadKnowledge = useCallback(async () => {
    setError(null);
    try {
      const payload = await fetchAIBrotherKnowledge(token);
      setDocuments(payload.documents);
      if (!selected && payload.documents[0]) {
        void openFile(payload.documents[0].path);
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }, [openFile, selected, token]);

  useEffect(() => {
    void loadKnowledge();
  }, [loadKnowledge]);

  useEffect(() => {
    if (!openRequest) return;
    setPendingOpenPath(openRequest.path);
  }, [openRequest]);

  useEffect(() => {
    if (!pendingOpenPath || documents.length === 0) return;
    const resolvedPath = resolveAIBrotherDocumentPath(documents, pendingOpenPath);
    if (!resolvedPath) {
      setError(`没有在知识库中找到：${pendingOpenPath}`);
      setPendingOpenPath(null);
      return;
    }
    setPendingOpenPath(null);
    void openFile(resolvedPath);
  }, [documents, openFile, pendingOpenPath]);

  const reindex = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await reindexAIBrotherKnowledge(token);
      setDocuments(result.documents);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <ThreadHeader
        title="课题组知识库"
        onToggleSidebar={onToggleSidebar}
        theme={theme}
        onToggleTheme={onToggleTheme}
        hideSidebarToggleOnDesktop={hideSidebarToggleOnDesktop}
      />

      <div className="grid min-h-0 flex-1 grid-cols-1 border-t border-border/60 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="min-h-0 border-b border-border/60 bg-muted/20 lg:border-b-0 lg:border-r">
          <div className="flex h-11 items-center justify-between px-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              <BookOpen className="h-4 w-4" />
              课题组知识库
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={reindex}
              disabled={loading}
              className="h-8 w-8 rounded-lg"
              title="重新索引"
            >
              <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            </Button>
          </div>
          <div className="h-[220px] overflow-auto px-2 pb-3 lg:h-[calc(100%-2.75rem)]">
            {grouped.map(([label, docs]) => (
              <section key={label} className="mb-3">
                <div className="px-2 py-1 text-[11px] font-medium text-muted-foreground">
                  {label}
                </div>
                <div className="space-y-1">
                  {docs.map((doc) => (
                    <button
                      key={doc.path}
                      type="button"
                      onClick={() => openFile(doc.path)}
                      className={cn(
                        "w-full rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-accent/60",
                        selected?.path === doc.path && "bg-accent text-accent-foreground",
                      )}
                    >
                      <div className="truncate font-medium">{doc.title}</div>
                      <div className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                        {doc.preview}
                      </div>
                    </button>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </aside>

        <section className="min-h-0 overflow-auto px-5 py-4">
          {error ? (
            <div className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          ) : null}
          {selected ? (
            <article className="mx-auto max-w-3xl">
              <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span>{selected.category_label}</span>
                <span>/</span>
                <span className="font-mono">{selected.path}</span>
              </div>
              <MarkdownText className="text-sm leading-7">{selected.content}</MarkdownText>
            </article>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              选择一个知识文档开始查看
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
