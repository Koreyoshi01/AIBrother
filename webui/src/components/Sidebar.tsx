import { useState, type ReactNode } from "react";
import {
  Archive,
  BookOpen,
  ListFilter,
  Menu,
  Search,
  Settings,
  SquarePen,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { ChatList } from "@/components/ChatList";
import { ConnectionBadge } from "@/components/ConnectionBadge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type {
  ChatSummary,
  SidebarSortMode,
  SidebarViewState,
} from "@/lib/types";
import { cn } from "@/lib/utils";

interface SidebarProps {
  sessions: ChatSummary[];
  activeKey: string | null;
  loading: boolean;
  onNewChat: () => void;
  onSelect: (key: string) => void;
  onRequestDelete: (key: string, label: string) => void;
  onTogglePin: (key: string) => void;
  onRequestRename: (key: string, label: string) => void;
  onToggleArchive: (key: string) => void;
  onOpenSettings: () => void;
  onOpenAIBrother: () => void;
  onOpenSearch: () => void;
  onToggleArchived: () => void;
  onUpdateView: (view: Partial<SidebarViewState>) => void;
  onCollapse: () => void;
  onExpand?: () => void;
  containActionMenus?: boolean;
  collapsed?: boolean;
  pinnedKeys?: string[];
  archivedKeys?: string[];
  titleOverrides?: Record<string, string>;
  runningChatIds?: string[];
  completedChatIds?: string[];
  viewState?: SidebarViewState;
  showArchived?: boolean;
  archivedCount?: number;
}

export function Sidebar(props: SidebarProps) {
  const { t } = useTranslation();
  const [menuPortalContainer, setMenuPortalContainer] =
    useState<HTMLElement | null>(null);
  const collapsed = Boolean(props.collapsed);
  const toggleLabel = t("thread.header.toggleSidebar");

  return (
    <nav
      ref={props.containActionMenus ? setMenuPortalContainer : undefined}
      aria-label={t("sidebar.navigation")}
      className="flex h-full w-full min-w-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground"
    >
      <div
        className={cn(
          "px-2.5 pt-4",
          collapsed ? "flex w-14 flex-col items-center px-0" : "",
        )}
      >
        {!collapsed ? (
          <div className="mb-5 px-1.5">
            <div className="text-[22px] font-bold leading-tight text-foreground">
              {t("app.brand")}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {t("app.brandSub")}
            </div>
          </div>
        ) : (
          <button
            type="button"
            aria-label={toggleLabel}
            title={toggleLabel}
            onClick={props.onExpand}
            className="mb-3 flex h-9 w-9 items-center justify-center rounded-xl transition-colors hover:bg-sidebar-accent/75"
          >
            <img
              src="/brand/person.png"
              alt=""
              className="h-7 w-7 select-none rounded-full object-cover"
              draggable={false}
            />
          </button>
        )}

        <SidebarActionButton
          collapsed={collapsed}
          label={t("sidebar.newChat")}
          onClick={props.onNewChat}
          icon={<SquarePen className="h-4 w-4" />}
          primary
        />
        <SidebarActionButton
          collapsed={collapsed}
          label={t("sidebar.searchAria")}
          onClick={props.onOpenSearch}
          icon={<Search className="h-4 w-4" />}
        />
        <SidebarActionButton
          collapsed={collapsed}
          label={t("sidebar.aibrother")}
          onClick={props.onOpenAIBrother}
          icon={<BookOpen className="h-4 w-4" />}
        />
        <SidebarViewMenu
          compact={collapsed}
          view={props.viewState}
          onUpdateView={props.onUpdateView}
        />
        {props.archivedCount && !collapsed ? (
          <SidebarActionButton
            collapsed={false}
            label={
              props.showArchived
                ? t("chat.hideArchived")
                : t("chat.showArchived")
            }
            onClick={props.onToggleArchived}
            icon={<Archive className="h-4 w-4" />}
          />
        ) : null}

        {!collapsed ? (
          <div className="mt-4 px-1.5 text-xs text-muted-foreground">
            {t("sidebar.historyLabel")}
          </div>
        ) : null}
      </div>

      <div
        className={cn(
          "flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden px-1 pt-1 transition-opacity duration-200",
          collapsed && "pointer-events-none opacity-0",
        )}
      >
        {!collapsed && (
          <ChatList
            sessions={props.sessions}
            activeKey={props.activeKey}
            loading={props.loading}
            emptyLabel={t("chat.noSessions")}
            onSelect={props.onSelect}
            onRequestDelete={props.onRequestDelete}
            onTogglePin={props.onTogglePin}
            onRequestRename={props.onRequestRename}
            onToggleArchive={props.onToggleArchive}
            pinnedKeys={props.pinnedKeys}
            archivedKeys={props.archivedKeys}
            titleOverrides={props.titleOverrides}
            runningChatIds={props.runningChatIds}
            completedChatIds={props.completedChatIds}
            density={props.viewState?.density}
            showPreviews={props.viewState?.show_previews}
            showTimestamps={props.viewState?.show_timestamps}
            sort={props.viewState?.sort}
            showArchived={props.showArchived}
            hideGroupLabels
            actionMenuPortalContainer={
              props.containActionMenus ? menuPortalContainer : undefined
            }
          />
        )}
      </div>

      <div
        className={cn(
          "flex items-center gap-1 border-t border-sidebar-border/80 px-2 py-2.5",
          collapsed && "w-14 flex-col px-0",
        )}
      >
        <SidebarActionButton
          collapsed={collapsed}
          label={t("sidebar.settings")}
          onClick={props.onOpenSettings}
          icon={<Settings className="h-4 w-4" />}
          className={collapsed ? undefined : "flex-1"}
        />
        {!collapsed ? <ConnectionBadge /> : null}
        {!collapsed ? (
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("sidebar.collapse")}
            onClick={props.onCollapse}
            className="h-8 w-8 shrink-0 rounded-lg text-muted-foreground/85 hover:bg-sidebar-accent/75 hover:text-sidebar-foreground"
          >
            <Menu className="h-3.5 w-3.5" />
          </Button>
        ) : null}
      </div>
    </nav>
  );
}

function SidebarActionButton({
  collapsed,
  label,
  icon,
  onClick,
  className,
  primary = false,
}: {
  collapsed: boolean;
  label: string;
  icon: ReactNode;
  onClick: () => void;
  className?: string;
  primary?: boolean;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      aria-label={label}
      title={collapsed ? label : undefined}
      onClick={onClick}
      className={cn(
        "group h-9 min-w-0 gap-2 overflow-hidden font-medium transition-colors",
        primary
          ? collapsed
            ? "w-9 justify-center rounded-xl bg-white px-0 shadow-[0_1px_2px_rgba(0,0,0,.06)] hover:bg-white/90"
            : "w-full justify-start rounded-[10px] bg-white px-3 text-[14px] text-foreground shadow-[0_1px_2px_rgba(0,0,0,.06)] hover:bg-white/90"
          : collapsed
            ? "w-9 justify-center rounded-xl px-0 text-sidebar-foreground/85 hover:bg-sidebar-accent/75"
            : "w-full justify-start rounded-[10px] px-3 text-[13px] text-sidebar-foreground/85 hover:bg-sidebar-accent/75 hover:text-sidebar-foreground",
        collapsed && !primary && "gap-0",
        className,
      )}
    >
      <span className="flex shrink-0 items-center justify-center" aria-hidden>
        {icon}
      </span>
      <span
        className={cn(
          "min-w-0 overflow-hidden truncate whitespace-nowrap transition-[max-width,opacity] duration-200",
          collapsed ? "max-w-0 opacity-0" : "max-w-[12rem] opacity-100",
        )}
      >
        {label}
      </span>
    </Button>
  );
}

function SidebarViewMenu({
  compact = false,
  view,
  onUpdateView,
}: {
  compact?: boolean;
  view?: SidebarViewState;
  onUpdateView: (view: Partial<SidebarViewState>) => void;
}) {
  const { t } = useTranslation();
  const sort = view?.sort ?? "updated_desc";
  const setSort = (value: string) => {
    if (isSidebarSortMode(value)) onUpdateView({ sort: value });
  };

  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          aria-label={t("sidebar.viewOptions")}
          title={compact ? t("sidebar.viewOptions") : undefined}
          className={cn(
            "h-9 min-w-0 overflow-hidden font-medium text-sidebar-foreground/85 hover:bg-sidebar-accent/75 hover:text-sidebar-foreground",
            compact
              ? "w-9 justify-center gap-0 rounded-xl px-0"
              : "w-full justify-start gap-2 rounded-[10px] px-3 text-[13px]",
          )}
          variant="ghost"
        >
          <ListFilter className="h-4 w-4 shrink-0" aria-hidden />
          <span
            className={cn(
              "min-w-0 overflow-hidden truncate whitespace-nowrap transition-[max-width,opacity] duration-200",
              compact ? "max-w-0 opacity-0" : "max-w-[12rem] opacity-100",
            )}
          >
            {t("sidebar.viewOptions")}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-52">
        <DropdownMenuLabel className="text-xs text-muted-foreground">
          {t("sidebar.viewOptions")}
        </DropdownMenuLabel>
        <DropdownMenuCheckboxItem
          checked={view?.density === "compact"}
          onCheckedChange={(checked) =>
            onUpdateView({ density: checked ? "compact" : "comfortable" })
          }
          onSelect={(event) => event.preventDefault()}
        >
          {t("sidebar.compactList")}
        </DropdownMenuCheckboxItem>
        <DropdownMenuCheckboxItem
          checked={Boolean(view?.show_previews)}
          onCheckedChange={(checked) =>
            onUpdateView({ show_previews: Boolean(checked) })
          }
          onSelect={(event) => event.preventDefault()}
        >
          {t("sidebar.showPreviews")}
        </DropdownMenuCheckboxItem>
        <DropdownMenuCheckboxItem
          checked={Boolean(view?.show_timestamps)}
          onCheckedChange={(checked) =>
            onUpdateView({ show_timestamps: Boolean(checked) })
          }
          onSelect={(event) => event.preventDefault()}
        >
          {t("sidebar.showTimestamps")}
        </DropdownMenuCheckboxItem>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-xs text-muted-foreground">
          {t("sidebar.sortLabel")}
        </DropdownMenuLabel>
        <DropdownMenuRadioGroup value={sort} onValueChange={setSort}>
          <DropdownMenuRadioItem value="updated_desc">
            {t("sidebar.sortUpdated")}
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="created_desc">
            {t("sidebar.sortCreated")}
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="title_asc">
            {t("sidebar.sortTitle")}
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function isSidebarSortMode(value: string): value is SidebarSortMode {
  return value === "updated_desc" || value === "created_desc" || value === "title_asc";
}
