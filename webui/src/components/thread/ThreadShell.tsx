import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ThreadComposer } from "@/components/thread/ThreadComposer";
import { ThreadHeader } from "@/components/thread/ThreadHeader";
import { StreamErrorNotice } from "@/components/thread/StreamErrorNotice";
import { ThreadViewport } from "@/components/thread/ThreadViewport";
import { useNanobotStream, type SendImage, type SendOptions } from "@/hooks/useNanobotStream";
import { useSessionHistory } from "@/hooks/useSessions";
import { fetchCliApps, fetchMcpPresets, fetchSettings, listSlashCommands } from "@/lib/api";
import {
  CLI_APPS_CHANGED_EVENT,
  installedCliAppsFromPayload,
  isCliAppsPayload,
} from "@/lib/cli-app-events";
import {
  MCP_PRESETS_CHANGED_EVENT,
  installedMcpPresetsFromPayload,
  isMcpPresetsPayload,
} from "@/lib/mcp-preset-events";
import { inferProviderFromModelName, providerDisplayLabel } from "@/lib/provider-brand";
import type { ChatSummary, CliAppInfo, McpPresetInfo, SettingsPayload, SlashCommand, UIMessage } from "@/lib/types";
import { normalizeLegacyLongTaskMessages } from "@/lib/thread-display-compat";
import { scrubSubagentUiMessages } from "@/lib/subagent-channel-display";
import { useClient } from "@/providers/ClientProvider";

function projectWebuiThreadMessages(messages: UIMessage[]): UIMessage[] {
  return scrubSubagentUiMessages(normalizeLegacyLongTaskMessages(messages));
}

function sameMessageShape(a: UIMessage, b: UIMessage): boolean {
  return (
    a.role === b.role
    && (a.kind ?? "") === (b.kind ?? "")
    && a.content === b.content
  );
}

function isStaleThreadSnapshot(current: UIMessage[], snapshot: UIMessage[]): boolean {
  if (current.length === 0 || snapshot.length >= current.length) return false;
  if (snapshot.length === 0) return true;
  return snapshot.every((message, index) => sameMessageShape(current[index], message));
}

interface ThreadShellProps {
  session: ChatSummary | null;
  title: string;
  onToggleSidebar: () => void;
  onGoHome?: () => void;
  onNewChat?: () => void;
  onCreateChat?: () => Promise<string | null>;
  onTurnEnd?: () => void;
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
  hideSidebarToggleOnDesktop?: boolean;
}

function toModelBadgeLabel(modelName: string | null): string | null {
  if (!modelName) return null;
  const trimmed = modelName.trim();
  if (!trimmed) return null;
  const leaf = trimmed.split("/").pop() ?? trimmed;
  return leaf || trimmed;
}

interface ModelBadgeInfo {
  label: string | null;
  provider: string | null;
  providerLabel: string | null;
}

function activeModelPreset(settings: SettingsPayload | null): SettingsPayload["model_presets"][number] | null {
  if (!settings) return null;
  const configured = settings.agent.model_preset || "default";
  return (
    settings.model_presets.find((preset) => preset.name === configured)
    ?? settings.model_presets.find((preset) => preset.active)
    ?? null
  );
}

function resolvedModelProvider(settings: SettingsPayload | null, modelName: string | null): string | null {
  const preset = activeModelPreset(settings);
  const rawProvider = preset?.provider || settings?.agent.provider || null;
  if (rawProvider === "auto") {
    return settings?.agent.resolved_provider || inferProviderFromModelName(modelName) || null;
  }
  return rawProvider || inferProviderFromModelName(modelName);
}

function toModelBadgeInfo(modelName: string | null, settings: SettingsPayload | null): ModelBadgeInfo {
  const label = toModelBadgeLabel(modelName || settings?.agent.model || null);
  const provider = resolvedModelProvider(settings, modelName || settings?.agent.model || null);
  return {
    label,
    provider,
    providerLabel: provider ? providerDisplayLabel(settings?.providers ?? [], provider) : null,
  };
}

const EXAMPLE_CHIP_KEYS = [
  "centrifuge",
  "abstract",
  "diary",
  "reaction",
] as const;

interface PendingFirstMessage {
  content: string;
  images?: SendImage[];
  options?: SendOptions;
}

export function ThreadShell({
  session,
  title,
  onToggleSidebar,
  onCreateChat,
  onTurnEnd,
  theme = "light",
  onToggleTheme = () => {},
  hideSidebarToggleOnDesktop = false,
}: ThreadShellProps) {
  const { t } = useTranslation();
  const chatId = session?.chatId ?? null;
  const historyKey = session?.key ?? null;
  const {
    messages: historical,
    loading,
    hasPendingToolCalls,
    refresh: refreshHistory,
    version: historyVersion,
  } = useSessionHistory(historyKey);
  const { client, modelName, token } = useClient();
  const [booting, setBooting] = useState(false);
  const [slashCommands, setSlashCommands] = useState<SlashCommand[]>([]);
  const [cliApps, setCliApps] = useState<CliAppInfo[]>([]);
  const [mcpPresets, setMcpPresets] = useState<McpPresetInfo[]>([]);
  const [settings, setSettings] = useState<SettingsPayload | null>(null);
  const [heroImageMode, setHeroImageMode] = useState(false);
  const [scrollToBottomSignal, setScrollToBottomSignal] = useState(0);
  const pendingFirstRef = useRef<PendingFirstMessage | null>(null);
  const messageCacheRef = useRef<Map<string, UIMessage[]>>(new Map());
  /** Last chatId we associated with the in-memory thread (for cache-on-switch). */
  const prevChatIdForCacheRef = useRef<string | null>(null);
  /** Skip one message-cache write right after chatId changes (messages may not match yet). */
  const skipLayoutCacheRef = useRef(false);
  const appliedHistoryVersionRef = useRef<Map<string, number>>(new Map());
  const pendingCanonicalHydrateRef = useRef<Set<string>>(new Set());
  const sessionKeyByChatIdRef = useRef<Map<string, string>>(new Map());

  const initial = useMemo(() => {
    if (!chatId) return historical;
    return messageCacheRef.current.get(chatId) ?? historical;
  }, [chatId, historical]);
  const handleTurnEnd = useCallback(() => {
    onTurnEnd?.();
  }, [onTurnEnd]);
  const {
    messages,
    isStreaming,
    runStartedAt,
    goalState,
    send,
    stop,
    setMessages,
    streamError,
    dismissStreamError,
  } = useNanobotStream(chatId, initial, hasPendingToolCalls, handleTurnEnd);

  useEffect(() => {
    if (chatId && historyKey) sessionKeyByChatIdRef.current.set(chatId, historyKey);
  }, [chatId, historyKey]);

  const displayMessages = useMemo(() => projectWebuiThreadMessages(messages), [messages]);

  const showHeroComposer = messages.length === 0 && !loading;
  const modelBadge = useMemo(
    () => toModelBadgeInfo(modelName, settings),
    [modelName, settings],
  );

  const refreshModelSettings = useCallback(async () => {
    try {
      setSettings(await fetchSettings(token));
    } catch {
      setSettings(null);
    }
  }, [token]);

  useEffect(() => {
    void refreshModelSettings();
  }, [refreshModelSettings]);

  useEffect(() => {
    return client.onRuntimeModelUpdate(() => {
      void refreshModelSettings();
    });
  }, [client, refreshModelSettings]);

  useEffect(() => {
    if (!chatId || loading) return;
    const cached = messageCacheRef.current.get(chatId);
    const appliedVersion = appliedHistoryVersionRef.current.get(chatId) ?? 0;
    const hasPendingCanonicalHydrate = pendingCanonicalHydrateRef.current.has(chatId);
    const hasNewCanonicalHistory = hasPendingCanonicalHydrate && historyVersion > appliedVersion;
    // When the user switches away and back, keep the local in-memory thread
    // state (including not-yet-persisted messages) instead of replacing it with
    // whatever the history endpoint currently knows about. Once a fresh
    // canonical replay arrives (e.g. after ``session_updated`` refresh), prefer it
    // so rendering converges to the same shape as a manual refresh.
    setMessages((prev) => {
      const normalizedHistory = projectWebuiThreadMessages(historical);
      const keepLiveMessages = (messagesToKeep: UIMessage[]) => {
        const projected = projectWebuiThreadMessages(messagesToKeep);
        messageCacheRef.current.set(chatId, projected);
        return projected;
      };
      if (hasNewCanonicalHistory && historical.length > 0) {
        if (isStaleThreadSnapshot(prev, normalizedHistory)) return keepLiveMessages(prev);
        pendingCanonicalHydrateRef.current.delete(chatId);
        appliedHistoryVersionRef.current.set(chatId, historyVersion);
        messageCacheRef.current.set(chatId, normalizedHistory);
        return normalizedHistory;
      }
      if (cached && cached.length > 0) {
        const normalizedCached = projectWebuiThreadMessages(cached);
        if (isStaleThreadSnapshot(prev, normalizedCached)) return keepLiveMessages(prev);
        return normalizedCached;
      }
      if (isStaleThreadSnapshot(prev, normalizedHistory)) return keepLiveMessages(prev);
      appliedHistoryVersionRef.current.set(chatId, historyVersion);
      if (normalizedHistory.length > 0) messageCacheRef.current.set(chatId, normalizedHistory);
      return normalizedHistory;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, chatId, historical, historyVersion]);

  useEffect(() => {
    if (!chatId) return;
    return client.onSessionUpdate((updatedChatId, scope) => {
      if (updatedChatId !== chatId) return;
      if (scope === "metadata") return;
      pendingCanonicalHydrateRef.current.add(chatId);
      refreshHistory();
    });
  }, [chatId, client, refreshHistory]);

  useEffect(() => {
    if (!chatId || loading) return;
    setScrollToBottomSignal((value) => value + 1);
  }, [chatId, loading, historical]);

  useEffect(() => {
    if (chatId) return;
    setMessages(projectWebuiThreadMessages(historical));
  }, [chatId, historical, setMessages]);

  useLayoutEffect(() => {
    if (chatId) {
      const prev = prevChatIdForCacheRef.current;
      if (prev && prev !== chatId) {
        messageCacheRef.current.set(prev, projectWebuiThreadMessages(messages));
        skipLayoutCacheRef.current = true;
      }
      prevChatIdForCacheRef.current = chatId;
    } else {
      if (prevChatIdForCacheRef.current) {
        messageCacheRef.current.set(
          prevChatIdForCacheRef.current,
          projectWebuiThreadMessages(messages),
        );
        skipLayoutCacheRef.current = true;
      }
      prevChatIdForCacheRef.current = null;
    }
  }, [chatId, messages]);

  // Persist thread to in-memory cache after paint so ``useNanobotStream``'s chat switch
  // ``useEffect`` reset has flushed; ``skipLayoutCacheRef`` drops the first run that still
  // sees the *previous* chat's ``messages`` (avoids stale rows leaking across sessions).
  useEffect(() => {
    if (!chatId) {
      return;
    }
    if (skipLayoutCacheRef.current) {
      skipLayoutCacheRef.current = false;
      return;
    }
    if (loading) {
      return;
    }
    messageCacheRef.current.set(chatId, projectWebuiThreadMessages(messages));
  }, [chatId, loading, messages]);

  useEffect(() => {
    if (!chatId) return;
    const pending = pendingFirstRef.current;
    if (!pending) return;
    pendingFirstRef.current = null;
    setScrollToBottomSignal((value) => value + 1);
    send(pending.content, pending.images, pending.options);
    setBooting(false);
  }, [chatId, send]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const commands = await listSlashCommands(token);
        if (!cancelled) setSlashCommands(commands);
      } catch {
        if (!cancelled) setSlashCommands([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const refreshCliApps = useCallback(async () => {
    try {
      const payload = await fetchCliApps(token);
      setCliApps(installedCliAppsFromPayload(payload));
    } catch {
      setCliApps([]);
    }
  }, [token]);

  const refreshMcpPresets = useCallback(async () => {
    try {
      const payload = await fetchMcpPresets(token);
      setMcpPresets(installedMcpPresetsFromPayload(payload));
    } catch {
      setMcpPresets([]);
    }
  }, [token]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const payload = await fetchCliApps(token);
        if (!cancelled) setCliApps(installedCliAppsFromPayload(payload));
      } catch {
        if (!cancelled) setCliApps([]);
      }
    };
    load();

    const refreshOnFocus = () => {
      if (document.visibilityState === "hidden") return;
      void refreshCliApps();
    };
    window.addEventListener("focus", refreshOnFocus);
    document.addEventListener("visibilitychange", refreshOnFocus);
    const refreshOnCliAppsChanged = (event: Event) => {
      const payload = (event as CustomEvent<unknown>).detail;
      if (isCliAppsPayload(payload)) {
        setCliApps(installedCliAppsFromPayload(payload));
        return;
      }
      void refreshCliApps();
    };
    window.addEventListener(CLI_APPS_CHANGED_EVENT, refreshOnCliAppsChanged);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", refreshOnFocus);
      document.removeEventListener("visibilitychange", refreshOnFocus);
      window.removeEventListener(CLI_APPS_CHANGED_EVENT, refreshOnCliAppsChanged);
    };
  }, [refreshCliApps, token]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const payload = await fetchMcpPresets(token);
        if (!cancelled) setMcpPresets(installedMcpPresetsFromPayload(payload));
      } catch {
        if (!cancelled) setMcpPresets([]);
      }
    };
    load();

    const refreshOnFocus = () => {
      if (document.visibilityState === "hidden") return;
      void refreshMcpPresets();
    };
    window.addEventListener("focus", refreshOnFocus);
    document.addEventListener("visibilitychange", refreshOnFocus);
    const refreshOnMcpPresetsChanged = (event: Event) => {
      const payload = (event as CustomEvent<unknown>).detail;
      if (isMcpPresetsPayload(payload)) {
        setMcpPresets(installedMcpPresetsFromPayload(payload));
        return;
      }
      void refreshMcpPresets();
    };
    window.addEventListener(MCP_PRESETS_CHANGED_EVENT, refreshOnMcpPresetsChanged);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", refreshOnFocus);
      document.removeEventListener("visibilitychange", refreshOnFocus);
      window.removeEventListener(MCP_PRESETS_CHANGED_EVENT, refreshOnMcpPresetsChanged);
    };
  }, [refreshMcpPresets, token]);

  const handleWelcomeSend = useCallback(
    async (content: string, images?: SendImage[], options?: SendOptions) => {
      if (booting) return;
      setBooting(true);
      pendingFirstRef.current = { content, images, options };
      const newId = await onCreateChat?.();
      if (!newId) {
        pendingFirstRef.current = null;
        setBooting(false);
      }
    },
    [booting, onCreateChat],
  );

  const handleThreadSend = useCallback(
    (content: string, images?: SendImage[], options?: SendOptions) => {
      setScrollToBottomSignal((value) => value + 1);
      send(content, images, options);
    },
    [send],
  );

  const handleQuickAction = useCallback(
    (prompt: string) => {
      const options: SendOptions | undefined = heroImageMode
        ? { imageGeneration: { enabled: true, aspect_ratio: null } }
        : undefined;
      if (session) {
        handleThreadSend(prompt, undefined, options);
        return;
      }
      void handleWelcomeSend(prompt, undefined, options);
    },
    [handleThreadSend, handleWelcomeSend, heroImageMode, session],
  );

  const quickActions = (
    <div className="mx-auto flex w-full max-w-[720px] flex-wrap justify-center gap-2 pt-3">
      {EXAMPLE_CHIP_KEYS.map((key) => {
        const label = t(`thread.empty.exampleChips.${key}.label`);
        const prompt = t(`thread.empty.exampleChips.${key}.prompt`);
        return (
          <button
            key={key}
            type="button"
            onClick={() => handleQuickAction(prompt)}
            disabled={booting || isStreaming}
            className="rounded-full border border-[#e8eaed] bg-[#f7f8fa] px-3.5 py-1.5 text-[13px] text-[#646a73] transition-colors hover:bg-[#eceef2] hover:text-foreground disabled:pointer-events-none disabled:opacity-60"
          >
            {label}
          </button>
        );
      })}
    </div>
  );

  const composer = (
    <>
      {streamError ? (
        <StreamErrorNotice
          error={streamError}
          onDismiss={dismissStreamError}
        />
      ) : null}
      {session ? (
        <ThreadComposer
          onSend={handleThreadSend}
          disabled={!chatId}
          isStreaming={isStreaming}
          placeholder={
            showHeroComposer
              ? t("thread.composer.placeholderHero")
              : t("thread.composer.placeholderThread")
          }
          modelLabel={modelBadge.label}
          modelProvider={modelBadge.provider}
          modelProviderLabel={modelBadge.providerLabel}
          variant={showHeroComposer ? "hero" : "thread"}
          slashCommands={slashCommands}
          cliApps={cliApps}
          mcpPresets={mcpPresets}
          imageMode={showHeroComposer ? heroImageMode : undefined}
          onImageModeChange={showHeroComposer ? setHeroImageMode : undefined}
          onStop={stop}
          runStartedAt={runStartedAt}
          goalState={goalState}
        />
      ) : (
        <ThreadComposer
          onSend={handleWelcomeSend}
          disabled={booting}
          isStreaming={isStreaming}
          placeholder={
            booting
              ? t("thread.composer.placeholderOpening")
              : t("thread.composer.placeholderHero")
          }
          modelLabel={modelBadge.label}
          modelProvider={modelBadge.provider}
          modelProviderLabel={modelBadge.providerLabel}
          variant="hero"
          slashCommands={slashCommands}
          cliApps={cliApps}
          mcpPresets={mcpPresets}
          imageMode={heroImageMode}
          onImageModeChange={setHeroImageMode}
          runStartedAt={runStartedAt}
          goalState={goalState}
        />
      )}
      {showHeroComposer ? quickActions : null}
    </>
  );

  const emptyState = loading ? (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      {t("thread.loadingConversation")}
    </div>
  ) : (
    <div className="flex w-full max-w-[560px] flex-col items-center text-center animate-in fade-in-0 slide-in-from-bottom-2 duration-500">
      <img
        src="/brand/person.png"
        alt=""
        className="mb-4 h-[180px] w-[180px] select-none object-contain"
        draggable={false}
      />
      <h1 className="text-[24px] font-semibold leading-[1.45] text-foreground">
        {t("thread.empty.greeting")}
      </h1>
    </div>
  );

  return (
    <section className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
      <ThreadHeader
        title={title}
        subtitle={t("thread.subtitle")}
        showTitle={!!session}
        onToggleSidebar={onToggleSidebar}
        theme={theme}
        onToggleTheme={onToggleTheme}
        hideSidebarToggleOnDesktop={hideSidebarToggleOnDesktop}
        minimal={!session && !loading}
      />
      <ThreadViewport
        messages={displayMessages}
        isStreaming={isStreaming}
        emptyState={emptyState}
        composer={composer}
        scrollToBottomSignal={scrollToBottomSignal}
        conversationKey={historyKey}
        showScrollToBottomButton={!!session}
        cliApps={cliApps}
        mcpPresets={mcpPresets}
      />
    </section>
  );
}
