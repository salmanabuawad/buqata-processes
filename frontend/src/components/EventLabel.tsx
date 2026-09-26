"use client";

import { useI18n } from "@/i18n/I18nProvider";
import { Badge } from "./ui";

export function EventLabel({ type, severity }: { type: string; severity?: string }) {
  const { t, has } = useI18n();
  const tone = severity === "CRITICAL" ? "danger" : severity === "WARNING" ? "warn" :
    type === "VAULT_OPENED" ? "sealed" : type.includes("DECISION") || type.includes("PROTOCOL") ? "success" : "neutral";
  return <Badge tone={tone}>{has(`events.${type}`) ? t(`events.${type}`) : type}</Badge>;
}

export function StatusBadge({ status, phase }: { status: string; phase?: string }) {
  const { t } = useI18n();
  const key = phase ?? status;
  const tone = key === "submission_open" ? "primary" : key === "awaiting_opening" ? "sealed" : key === "evaluation" ? "warn" :
    key === "decided" || key === "closed" ? "success" : key === "cancelled" ? "danger" : "neutral";
  return <Badge tone={tone}>{t(`phase.${key}`)}</Badge>;
}
