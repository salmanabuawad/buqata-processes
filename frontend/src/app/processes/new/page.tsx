"use client";

import { useEffect, useState } from "react";
import { Award, FileSearch, Gavel, HandCoins, Megaphone, UsersRound } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { CategoryPicker } from "@/components/CategoryPicker";
import { Alert, Badge, Button, Card, CardHeader, cx, ErrorAlert, Field, Input, PageHeader, Textarea } from "@/components/ui";
import { useI18n } from "@/i18n/I18nProvider";
import { api } from "@/lib/api";

interface Preview { count: number; suppliers: { id: string; company_name: string; city: string; relations: string[] }[] }

function toLocalInput(date: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function TypeCards({ onPick }: { onPick: (key: string) => void }) {
  const { t } = useI18n();
  const types = [
    { key: "rfq", icon: <FileSearch className="size-6" />, available: true },
    { key: "tender", icon: <Gavel className="size-6" />, available: false, phase: 7 },
    { key: "scholarship", icon: <Award className="size-6" />, available: false, phase: 8 },
    { key: "call_for_proposals", icon: <Megaphone className="size-6" />, available: false },
    { key: "support", icon: <HandCoins className="size-6" />, available: false },
    { key: "recruitment", icon: <UsersRound className="size-6" />, available: false },
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {types.map((ty) => (
        <button
          key={ty.key}
          onClick={() => ty.available && onPick(ty.key)}
          disabled={!ty.available}
          className={cx(
            "rounded-xl border bg-surface p-5 text-start transition-all",
            ty.available ? "border-line hover:border-primary hover:shadow-md" : "cursor-not-allowed border-dashed border-line-strong opacity-70",
          )}
        >
          <div className="flex items-center justify-between">
            <div className={cx("flex size-11 items-center justify-center rounded-lg", ty.available ? "bg-primary-soft text-primary" : "bg-surface-2 text-muted")}>{ty.icon}</div>
            {!ty.available && <Badge>{ty.phase ? t("new.coming_phase", { phase: ty.phase }) : t("new.planned")}</Badge>}
          </div>
          <div className="mt-3 font-semibold">{t(`types.${ty.key}`)}</div>
          <div className="mt-1 text-sm text-muted">{t(`new.desc_${ty.key}`)}</div>
        </button>
      ))}
    </div>
  );
}

function RFQForm() {
  const { t } = useI18n();
  const inAWeek = new Date(Date.now() + 7 * 86400_000);
  inAWeek.setHours(12, 0, 0, 0);
  const [form, setForm] = useState({
    title: "", description: "", quantity: "1", unit: "יח'", technical_specification: "", additional_requirements: "",
    expected_delivery_date: "", deadline: toLocalInput(inAWeek), contact_name: "", contact_email: "", contact_phone: "",
  });
  const [categories, setCategories] = useState<string[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [showList, setShowList] = useState(false);
  const [busy, setBusy] = useState<"" | "draft" | "publish">("");
  const [error, setError] = useState<unknown>(null);
  const [confirm, setConfirm] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });

  useEffect(() => {
    if (!categories.length) { setPreview(null); return; }
    const handle = setTimeout(() => {
      api.post<Preview>("/distribution/preview", { category_ids: categories }).then(setPreview).catch(() => setPreview(null));
    }, 250);
    return () => clearTimeout(handle);
  }, [categories]);

  const save = async (publish: boolean) => {
    setBusy(publish ? "publish" : "draft");
    setError(null);
    try {
      const created = await api.post<{ id: string }>("/processes", {
        process_type: "rfq", title: form.title, description: form.description, category_ids: categories,
        submission_deadline: new Date(form.deadline).toISOString(),
        details: {
          quantity: Number(form.quantity), unit: form.unit, technical_specification: form.technical_specification,
          additional_requirements: form.additional_requirements, expected_delivery_date: form.expected_delivery_date || null,
        },
        contact_name: form.contact_name, contact_email: form.contact_email, contact_phone: form.contact_phone,
      });
      for (const file of files) {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("kind", "specification");
        fd.append("title", file.name);
        await api.form(`/processes/${created.id}/documents`, fd);
      }
      if (publish) await api.post(`/processes/${created.id}/publish`, {});
      window.location.href = `/process/?id=${created.id}`;
    } catch (err) {
      setError(err);
      setConfirm(false);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
      <div className="space-y-6">
        <ErrorAlert error={error} />
        <Card>
          <CardHeader title={t("new.section_request")} />
          <div className="grid gap-4 p-5 sm:grid-cols-2">
            <div className="sm:col-span-2"><Field label={t("rfq.title")} required>{(id) => <Input id={id} value={form.title} onChange={set("title")} placeholder={t("rfq.title_placeholder")} />}</Field></div>
            <div className="sm:col-span-2"><Field label={t("rfq.description")}>{(id) => <Textarea id={id} value={form.description} onChange={set("description")} />}</Field></div>
            <Field label={t("rfq.quantity")} required>{(id) => <Input id={id} type="number" min={1} value={form.quantity} onChange={set("quantity")} />}</Field>
            <Field label={t("rfq.unit")}>{(id) => <Input id={id} value={form.unit} onChange={set("unit")} />}</Field>
            <div className="sm:col-span-2"><Field label={t("rfq.technical_specification")}>{(id) => <Textarea id={id} rows={5} value={form.technical_specification} onChange={set("technical_specification")} />}</Field></div>
            <div className="sm:col-span-2"><Field label={t("rfq.additional_requirements")}>{(id) => <Textarea id={id} value={form.additional_requirements} onChange={set("additional_requirements")} />}</Field></div>
            <div className="sm:col-span-2">
              <Field label={t("rfq.attachments")} hint={t("rfq.attachments_hint")}>
                {(id) => <Input id={id} type="file" multiple accept=".pdf,.docx,.xlsx,.doc,.xls,.zip" className="h-auto py-1.5" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />}
              </Field>
            </div>
          </div>
        </Card>
        <Card>
          <CardHeader title={t("new.section_schedule")} />
          <div className="grid gap-4 p-5 sm:grid-cols-2">
            <Field label={t("rfq.deadline")} hint={t("rfq.deadline_hint")} required>{(id) => <Input id={id} type="datetime-local" value={form.deadline} onChange={set("deadline")} dir="ltr" />}</Field>
            <Field label={t("rfq.expected_delivery")}>{(id) => <Input id={id} type="date" value={form.expected_delivery_date} onChange={set("expected_delivery_date")} dir="ltr" />}</Field>
            <Field label={t("rfq.contact_name")}>{(id) => <Input id={id} value={form.contact_name} onChange={set("contact_name")} />}</Field>
            <Field label={t("rfq.contact_email")}>{(id) => <Input id={id} type="email" dir="ltr" value={form.contact_email} onChange={set("contact_email")} />}</Field>
            <Field label={t("rfq.contact_phone")}>{(id) => <Input id={id} type="tel" dir="ltr" value={form.contact_phone} onChange={set("contact_phone")} />}</Field>
          </div>
        </Card>
      </div>

      <div className="space-y-6 xl:sticky xl:top-22 xl:self-start">
        <Card>
          <CardHeader title={t("new.section_categories")} subtitle={t("new.categories_hint")} />
          <div className="p-4"><CategoryPicker value={categories} onChange={setCategories} max={20} /></div>
        </Card>
        <Card className="border-primary/30">
          <div className="p-5">
            <div className="text-sm text-muted">{t("new.matching_title")}</div>
            <div className="mt-1 text-4xl font-bold text-primary">{preview ? preview.count : "—"}</div>
            <div className="mt-1 text-sm text-ink-2">{preview ? t("new.matching_sentence", { count: preview.count }) : t("new.matching_empty")}</div>
            <Alert tone="success">{t("new.fairness_rule")}</Alert>
            {preview && preview.count > 0 && (
              <div className="mt-3">
                <button className="text-sm text-primary underline" onClick={() => setShowList((v) => !v)}>{showList ? t("new.hide_list") : t("new.show_list")}</button>
                {showList && (
                  <ul className="mt-2 max-h-60 divide-y divide-line overflow-y-auto rounded-lg border border-line text-sm">
                    {preview.suppliers.map((s) => (
                      <li key={s.id} className="flex items-center justify-between gap-2 px-3 py-2">
                        <span>{s.company_name}<span className="block text-xs text-muted">{s.city}</span></span>
                        <span className="text-xs text-muted">{s.relations.map((r) => t(`match.${r}`)).join(", ")}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="mt-2 text-xs text-muted">{t("new.list_read_only")}</p>
              </div>
            )}
          </div>
          <div className="flex flex-col gap-2 border-t border-line p-4">
            {!confirm ? (
              <Button onClick={() => setConfirm(true)} disabled={!form.title || !categories.length || !!busy}>{t("new.publish")}</Button>
            ) : (
              <div className="space-y-2 rounded-lg bg-primary-soft p-3">
                <p className="text-sm">{t("new.publish_confirm", { count: preview?.count ?? 0 })}</p>
                <div className="flex gap-2">
                  <Button onClick={() => save(true)} busy={busy === "publish"}>{t("new.publish_now")}</Button>
                  <Button variant="ghost" onClick={() => setConfirm(false)}>{t("common.cancel")}</Button>
                </div>
              </div>
            )}
            <Button variant="secondary" onClick={() => save(false)} busy={busy === "draft"} disabled={!form.title || !!busy}>{t("new.save_draft")}</Button>
          </div>
        </Card>
      </div>
    </div>
  );
}

export default function NewProcessPage() {
  const { t } = useI18n();
  const [type, setType] = useState<string | null>(null);
  return (
    <AppShell>
      <PageHeader title={type ? t("new.title_rfq") : t("new.title")} subtitle={type ? t("new.subtitle_rfq") : t("new.subtitle")}
        actions={type && <Button variant="ghost" onClick={() => setType(null)}>{t("new.change_type")}</Button>} />
      {!type ? <TypeCards onPick={setType} /> : <RFQForm />}
    </AppShell>
  );
}
