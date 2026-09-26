"use client";

import { useEffect, useState } from "react";
import { Eye, Lock, LockKeyhole, Search } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";
import { api } from "@/lib/api";
import { Button, cx, Field, Input, Modal, Spinner } from "./ui";

export type OpeningMode = "visible" | "sealed_anytime" | "sealed_after_deadline";
export const OPENING_MODES: OpeningMode[] = ["visible", "sealed_anytime", "sealed_after_deadline"];

const ICONS: Record<OpeningMode, React.ReactNode> = {
  visible: <Eye className="size-5" />,
  sealed_anytime: <LockKeyhole className="size-5" />,
  sealed_after_deadline: <Lock className="size-5" />,
};

/** Chosen when the request is created; changeable while it is a draft. */
export function OpeningModePicker({ value, onChange, disabled }: { value: OpeningMode; onChange: (m: OpeningMode) => void; disabled?: boolean }) {
  const { t } = useI18n();
  return (
    <div role="radiogroup" aria-label={t("opening_mode.title")} className="grid gap-3 md:grid-cols-3">
      {OPENING_MODES.map((mode) => (
        <label
          key={mode}
          className={cx(
            "flex cursor-pointer flex-col gap-1 rounded-lg border p-3 text-sm transition-colors",
            value === mode ? "border-primary bg-primary-soft" : "border-line-strong hover:bg-surface-2",
            disabled && "cursor-not-allowed opacity-60",
          )}
        >
          <span className="flex items-center gap-2 font-medium">
            <input type="radio" name="opening_mode" className="size-4 accent-[var(--primary)]" checked={value === mode}
              disabled={disabled} onChange={() => onChange(mode)} />
            <span className={value === mode ? "text-primary" : "text-muted"}>{ICONS[mode]}</span>
            {t(`opening_mode.${mode}`)}
          </span>
          <span className="text-xs text-muted">{t(`opening_mode.${mode}_hint`)}</span>
        </label>
      ))}
    </div>
  );
}

export function OpeningModeBadge({ mode }: { mode: string | null | undefined }) {
  const { t } = useI18n();
  if (!mode) return null;
  const m = mode as OpeningMode;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface-2 px-2.5 py-0.5 text-xs text-ink-2">
      {ICONS[m] && <span className="[&_svg]:size-3.5">{ICONS[m]}</span>}{t(`opening_mode.${m}`)}
    </span>
  );
}

interface SupplierHit { id: string; company_name: string; city: string; status: string; categories: string[] }

/** Search the registry and pick one active supplier, with a mandatory reason. */
export function AddSupplierModal({ open, onClose, onConfirm, excludeIds, busy, error }: {
  open: boolean; onClose: () => void; onConfirm: (supplierId: string, name: string, reason: string) => void;
  excludeIds: string[]; busy?: boolean; error?: React.ReactNode;
}) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SupplierHit[] | null>(null);
  const [picked, setPicked] = useState<SupplierHit | null>(null);
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (!open) { setQ(""); setPicked(null); setReason(""); return; }
    const handle = setTimeout(() => {
      const params = new URLSearchParams({ status: "ACTIVE", limit: "30" });
      if (q) params.set("q", q);
      api.get<{ items: SupplierHit[] }>(`/suppliers?${params}`).then((r) => setHits(r.items)).catch(() => setHits([]));
    }, 200);
    return () => clearTimeout(handle);
  }, [q, open]);

  return (
    <Modal open={open} onClose={onClose} title={t("distribution_edit.add_title")}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
        <Button onClick={() => picked && onConfirm(picked.id, picked.company_name, reason)} busy={busy}
          disabled={!picked || reason.trim().length < 5}>{t("distribution_edit.add")}</Button>
      </>}>
      <div className="space-y-4">
        <div className="relative">
          <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("registry.search")} className="ps-9" aria-label={t("registry.search")} />
        </div>
        <div className="max-h-64 overflow-y-auto rounded-lg border border-line">
          {!hits ? <Spinner /> : hits.filter((h) => !excludeIds.includes(h.id)).map((h) => (
            <button type="button" key={h.id} onClick={() => setPicked(h)}
              className={cx("block w-full border-b border-line px-3 py-2 text-start text-sm last:border-0 hover:bg-surface-2",
                picked?.id === h.id && "bg-primary-soft")}>
              <span className="font-medium">{h.company_name}</span>
              <span className="block text-xs text-muted">{h.city} · {h.categories.join(" · ")}</span>
            </button>
          ))}
        </div>
        <Field label={t("distribution_edit.reason")} hint={t("distribution_edit.reason_hint")} required>
          {(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}
        </Field>
        {error}
      </div>
    </Modal>
  );
}
