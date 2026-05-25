import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  FileText,
  FlaskConical,
  GraduationCap,
  Presentation,
  RefreshCw,
  Search,
  Send,
} from "lucide-react";

import { MarkdownText } from "@/components/MarkdownText";
import { ThreadHeader } from "@/components/thread/ThreadHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useClient } from "@/providers/ClientProvider";
import {
  askAIBrother,
  fetchAIBrotherFile,
  fetchAIBrotherKnowledge,
  reindexAIBrotherKnowledge,
  searchAIBrotherKnowledge,
} from "@/lib/api";
import { resolveAIBrotherDocumentPath } from "@/lib/aibrother-links";
import type {
  AIBrotherAskResponse,
  AIBrotherDocument,
  AIBrotherEvidence,
  AIBrotherFile,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const MODES = [
  { id: "experiment", label: "做实验", icon: FlaskConical },
  { id: "paper", label: "写论文", icon: GraduationCap },
  { id: "presentation", label: "做汇报", icon: Presentation },
  { id: "journal", label: "做日记", icon: FileText },
];

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
  const [query, setQuery] = useState("CO2 吸收 试剂比例");
  const [mode, setMode] = useState("experiment");
  const [evidence, setEvidence] = useState<AIBrotherEvidence[]>([]);
  const [answer, setAnswer] = useState<AIBrotherAskResponse | null>(null);
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

  const runSearch = useCallback(async () => {
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    try {
      const result = await searchAIBrotherKnowledge(token, q, 10);
      setEvidence(result.evidence);
      setAnswer(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [query, token]);

  const runAsk = useCallback(async () => {
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    try {
      const result = await askAIBrother(token, q, mode);
      setAnswer(result);
      setEvidence(result.evidence);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [mode, query, token]);

  const reindex = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await reindexAIBrotherKnowledge(token);
      setDocuments(result.documents);
      await runSearch();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [runSearch, token]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <ThreadHeader
        title="AI大师兄"
        onToggleSidebar={onToggleSidebar}
        theme={theme}
        onToggleTheme={onToggleTheme}
        hideSidebarToggleOnDesktop={hideSidebarToggleOnDesktop}
      />

      <div className="grid min-h-0 flex-1 grid-cols-1 border-t border-border/60 lg:grid-cols-[280px_minmax(0,1fr)_380px]">
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

        <aside className="min-h-0 border-t border-border/60 bg-muted/15 lg:border-l lg:border-t-0">
          <div className="flex h-full min-h-0 flex-col gap-3 p-3">
            <div className="grid grid-cols-4 gap-1">
              {MODES.map((item) => {
                const Icon = item.icon;
                return (
                  <Button
                    key={item.id}
                    type="button"
                    variant={mode === item.id ? "secondary" : "ghost"}
                    onClick={() => setMode(item.id)}
                    className="h-9 gap-1 rounded-md px-1 text-xs"
                    title={item.label}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    <span className="truncate">{item.label}</span>
                  </Button>
                );
              })}
            </div>

            <div className="flex gap-2">
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void runSearch();
                }}
                placeholder="搜索组内经验、实验手册、论文摘要"
                className="h-9"
              />
              <Button
                type="button"
                size="icon"
                onClick={runSearch}
                disabled={loading}
                className="h-9 w-9 rounded-md"
                title="检索"
              >
                <Search className="h-4 w-4" />
              </Button>
            </div>

            <Textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="min-h-[86px] resize-none"
              placeholder="问 AI大师兄：我要做 CO2 吸收实验，试剂比例是多少？"
            />
            <Button
              type="button"
              onClick={runAsk}
              disabled={loading || !query.trim()}
              className="h-9 gap-2 rounded-md"
            >
              <Send className="h-4 w-4" />
              基于证据生成回答
            </Button>

            {error ? (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            ) : null}

            <div className="min-h-0 flex-1 overflow-auto">
              {answer ? (
                <div className="mb-3 rounded-md border border-border/70 bg-background px-3 py-3">
                  <div className="mb-2 text-xs font-medium text-muted-foreground">
                    AI大师兄回答
                  </div>
                  <MarkdownText className="text-sm leading-6">{answer.answer}</MarkdownText>
                </div>
              ) : null}

              <div className="mb-2 text-xs font-medium text-muted-foreground">
                Evidence Pack
              </div>
              <div className="space-y-2">
                {evidence.length ? (
                  evidence.map((item, index) => (
                    <button
                      key={`${item.path}:${item.line}:${index}`}
                      type="button"
                      onClick={() => openFile(item.path)}
                      className="w-full rounded-md border border-border/70 bg-background px-3 py-2 text-left transition-colors hover:border-foreground/25"
                    >
                      <div className="flex items-center justify-between gap-2 text-xs">
                        <span className="font-medium">{item.category_label}</span>
                        <span className="font-mono text-muted-foreground">
                          {item.path}:{item.line}
                        </span>
                      </div>
                      <div className="mt-1 text-sm font-medium">{item.title}</div>
                      <div className="mt-1 line-clamp-3 text-xs leading-5 text-muted-foreground">
                        {item.snippet}
                      </div>
                    </button>
                  ))
                ) : (
                  <div className="rounded-md border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
                    搜索或提问后，这里会显示可点击来源。
                  </div>
                )}
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
