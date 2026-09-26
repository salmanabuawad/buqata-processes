"use client";

import { Check } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";
import { formatDateTime } from "@/lib/api";
import { cx } from "./ui";

export interface Stage { key: string; state: "done" | "current" | "pending"; at: string | null }

export function Timeline({ stages }: { stages: Stage[] }) {
  const { t, locale } = useI18n();
  return (
    <ol className="flex overflow-x-auto pb-1" aria-label={t("process.timeline")}>
      {stages.map((s, i) => (
        <li key={s.key} className="relative flex min-w-[112px] flex-1 flex-col items-center text-center" aria-current={s.state === "current" ? "step" : undefined}>
          {i > 0 && (
            // Connector from the previous step's centre to this one's; logical inset keeps it right in RTL.
            <span aria-hidden className={cx("absolute top-4 h-0.5 w-full", s.state === "pending" ? "bg-line" : "bg-accent")}
              style={{ insetInlineEnd: "50%" }} />
          )}
          <span className={cx(
            "relative z-10 flex size-8 items-center justify-center rounded-full border-2 text-xs font-semibold",
            s.state === "done" && "border-accent bg-accent text-white",
            s.state === "current" && "border-primary bg-primary-soft text-primary ring-4 ring-primary/15",
            s.state === "pending" && "border-line-strong bg-surface text-muted",
          )}>
            {s.state === "done" ? <Check className="size-4" /> : i + 1}
          </span>
          <span className={cx("mt-2 px-1 text-xs font-medium", s.state === "pending" ? "text-muted" : "text-ink")}>{t(`timeline.${s.key}`)}</span>
          {s.at && <span className="ltr mt-0.5 text-[11px] text-muted">{formatDateTime(s.at, locale)}</span>}
        </li>
      ))}
    </ol>
  );
}
