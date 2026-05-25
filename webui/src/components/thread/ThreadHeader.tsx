import { Menu, Moon, Sun } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ThreadHeaderProps {
  title: string;
  subtitle?: string;
  showTitle?: boolean;
  onToggleSidebar: () => void;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  hideSidebarToggleOnDesktop?: boolean;
  minimal?: boolean;
}

export function ThreadHeader({
  title,
  subtitle,
  showTitle = true,
  onToggleSidebar,
  theme,
  onToggleTheme,
  hideSidebarToggleOnDesktop = false,
  minimal = false,
}: ThreadHeaderProps) {
  const { t } = useTranslation();
  const resolvedSubtitle = subtitle ?? t("thread.subtitle");

  return (
    <div className="relative z-10 shrink-0 px-3 pb-1 pt-2">
      <div className="relative flex min-h-9 items-center justify-center">
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("thread.header.toggleSidebar")}
          onClick={onToggleSidebar}
          className={cn(
            "absolute left-0 h-7 w-7 rounded-md text-muted-foreground hover:bg-accent/35 hover:text-foreground",
            hideSidebarToggleOnDesktop && "lg:hidden",
          )}
        >
          <Menu className="h-3.5 w-3.5" />
        </Button>

        <div className="flex max-w-[min(70vw,32rem)] flex-col items-center px-10 text-center">
          {showTitle && !minimal ? (
            <h2 className="truncate text-[15px] font-semibold leading-tight text-foreground">
              {title}
            </h2>
          ) : null}
          <p className="mt-0.5 text-[11px] leading-tight text-[#b0b4bb]">
            {resolvedSubtitle}
          </p>
        </div>

        <ThemeButton
          theme={theme}
          onToggleTheme={onToggleTheme}
          label={t("thread.header.toggleTheme")}
          className="absolute right-0"
        />
      </div>
    </div>
  );
}

function ThemeButton({
  theme,
  onToggleTheme,
  label,
  className,
}: {
  theme: "light" | "dark";
  onToggleTheme: () => void;
  label: string;
  className?: string;
}) {
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={label}
      onClick={onToggleTheme}
      className={cn(
        "h-8 w-8 rounded-full text-muted-foreground/85 hover:bg-accent/40 hover:text-foreground",
        className,
      )}
    >
      {theme === "dark" ? (
        <Sun className="h-4 w-4" />
      ) : (
        <Moon className="h-4 w-4" />
      )}
    </Button>
  );
}
