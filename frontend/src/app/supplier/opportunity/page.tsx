"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, FileText, Lock, ShieldCheck, Upload } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/EventLabel";
import { Alert, Badge, Button, Card, CardHeader, ErrorAlert, Field, Input, KeyValue, PageHeader, Spinner, Textarea } from "@/components/ui";
import { useI18n } from "@/i18n/I18nProvider";
import { agorotToShekels, api, formatBytes, formatDate, formatDateTime } from "@/lib/api";
import { useQueryParam } from "@/lib/session";

interface ProcessView {
  id: string; reference_number: string; title: string; description: string; status: string; phase: string; process_type: string;
  details: { quantity?: number; unit?: string; technical_specification?: string; expected_delivery_date?: string; additional_requirements?: string };
  submission_deadline: string; categories: { id: string; path: string }[]; contact: { name: string; email: string; phone: string };
  documents: { id: string; title: string; size_bytes: number }[];
  document_requirements: { kind: string; required: boolean; extensions: string[]; multiple: boolean; names: Record<string, string> }[];
  server_time: string; content_sealed: boolean; opening_mode: string | null;
}

interface Receipt {
  receipt_number: string; status: string; submitted_at: string | null;
  current_version: { version_no: number; submitted_at: string; payload_hash: string; receipt_hash: string; files: { kind: string; filename: string; size_bytes: number; sha256: string }[] } | null;
  superseded_versions: { version_no: number; submitted_at: string; receipt_hash: string }[];
}

function ReceiptCard({ r, reference, sealed }: { r: Receipt; reference: string; sealed: boolean }) {
  const { t, locale } = useI18n();
  if (!r.current_version) return null;
  return (
    <Card className="border-sealed/30">
      <CardHeader title={t("submit.receipt_title")} subtitle={t("submit.receipt_hint")} icon={<ShieldCheck className="size-5 text-sealed" />}
        actions={<Button variant="secondary" size="sm" onClick={() => window.print()}>{t("submit.print")}</Button>} />
      <div className="space-y-4 p-5">
        <KeyValue items={[
          [t("submit.reference"), <span key="a" className="ltr">{reference}</span>],
          [t("submit.receipt_number"), <span key="b" className="ltr font-medium">{r.receipt_number}</span>],
          [t("submit.submitted_at"), <span key="c" className="ltr">{formatDateTime(r.current_version.submitted_at, locale)}</span>],
          [t("submit.version"), String(r.current_version.version_no)],
          [t("submit.receipt_hash"), <span key="d" className="hash">{r.current_version.receipt_hash}</span>],
        ]} />
        <ul className="divide-y divide-line rounded-lg border border-line text-sm">
          {r.current_version.files.map((f, i) => (
            <li key={i} className="px-3 py-2">
              <div className="flex items-center gap-2"><FileText className="size-4 text-muted" />{f.filename}<span className="text-xs text-muted">({formatBytes(f.size_bytes)})</span><Badge>{t(`docs.${f.kind}`)}</Badge></div>
              <div className="hash mt-1 text-muted">SHA-256 {f.sha256}</div>
            </li>
          ))}
        </ul>
        {sealed
          ? <Alert tone="sealed" title={t("submit.sealed_title")}>{t("submit.sealed_body")}</Alert>
          : <Alert tone="primary" title={t("submit.visible_title")}>{t("submit.visible_body")}</Alert>}
      </div>
    </Card>
  );
}

export default function OpportunityPage() {
  const { t, locale, pick } = useI18n();
  const id = useQueryParam("id");
  const [p, setP] = useState<ProcessView | null>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [vatRate, setVatRate] = useState(18);
  const [form, setForm] = useState({ price: "", delivery_days: "", warranty_months: "", payment_terms: "", notes: "" });
  const [files, setFiles] = useState<Record<string, File[]>>({});
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [editing, setEditing] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const view = await api.get<ProcessView>(`/processes/${id}`);
      setP(view);
      setReceipt(await api.get<Receipt | null>(`/processes/${id}/submission`));
      if (view.phase === "submission_open") await api.post(`/processes/${id}/submission/start`).catch(() => undefined);
    } catch (err) { setError(err); }
  }, [id]);
  useEffect(() => { void load(); api.get<{ vat_rate_percent: number }>("/meta").then((m) => setVatRate(m.vat_rate_percent)); }, [load]);

  const priceAgorot = Math.round(Number(form.price || 0) * 100);
  const vat = Math.round((priceAgorot * vatRate) / 100);

  const submit = async () => {
    if (!p) return;
    setBusy(true);
    setError(null);
    const fd = new FormData();
    fd.append("payload", JSON.stringify({
      price_before_vat_agorot: priceAgorot, delivery_days: Number(form.delivery_days), warranty_months: Number(form.warranty_months),
      payment_terms: form.payment_terms, notes: form.notes,
    }));
    for (const [kind, list] of Object.entries(files)) for (const f of list) { fd.append("kinds", kind); fd.append("files", f); }
    try {
      const r = await api.form<Receipt>(`/processes/${p.id}/submission`, fd);
      setReceipt(r);
      setEditing(false);
      setConfirm(false);
      setFiles({});
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(err);
      setConfirm(false);
    } finally { setBusy(false); }
  };

  if (!p) return <AppShell>{error ? <ErrorAlert error={error} /> : <Spinner />}</AppShell>;
  const open = p.phase === "submission_open";
  const hasSubmitted = !!receipt?.current_version;
  const showForm = open && (!hasSubmitted || editing);
  const requiredOk = p.document_requirements.filter((r) => r.required).every((r) => (files[r.kind]?.length ?? 0) > 0);

  return (
    <AppShell>
      <PageHeader eyebrow={<span className="ltr">{p.reference_number}</span>} title={p.title}
        actions={<StatusBadge status={p.status} phase={p.phase} />} />
      <div className="grid gap-6 xl:grid-cols-[1.3fr_1fr]">
        <div className="space-y-6">
          {error ? <ErrorAlert error={error} /> : null}
          {receipt && hasSubmitted && <ReceiptCard r={receipt} reference={p.reference_number} sealed={p.content_sealed} />}
          {hasSubmitted && open && !editing && (
            <Card className="flex flex-wrap items-center justify-between gap-3 p-5">
              <p className="text-sm text-ink-2">{t("submit.replace_hint")}</p>
              <Button variant="secondary" onClick={() => setEditing(true)}>{t("submit.replace")}</Button>
            </Card>
          )}
          {!open && !hasSubmitted && <Alert tone="warn" title={t("submit.closed_title")}>{t("submit.closed_body")}</Alert>}
          {p.status !== "PUBLISHED" && hasSubmitted && <Alert tone="success" title={t("submit.opened_title")}>{t("submit.opened_body")}</Alert>}

          {showForm && (
            <Card>
              <CardHeader title={hasSubmitted ? t("submit.new_version") : t("submit.title")} subtitle={t("submit.subtitle")} />
              <div className="space-y-5 p-5">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label={t("submit.price")} hint={t("submit.price_hint")} required>
                    {(fid) => <Input id={fid} type="number" min="0" step="0.01" dir="ltr" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} />}
                  </Field>
                  <div className="rounded-lg bg-surface-2 p-3 text-sm">
                    <div className="flex justify-between"><span className="text-muted">{t("submit.vat", { rate: vatRate })}</span><span className="ltr">{agorotToShekels(vat, locale)}</span></div>
                    <div className="mt-1 flex justify-between font-semibold"><span>{t("submit.total")}</span><span className="ltr">{agorotToShekels(priceAgorot + vat, locale)}</span></div>
                  </div>
                  <Field label={t("submit.delivery_days")} required>{(fid) => <Input id={fid} type="number" min="0" dir="ltr" value={form.delivery_days} onChange={(e) => setForm({ ...form, delivery_days: e.target.value })} />}</Field>
                  <Field label={t("submit.warranty_months")} required>{(fid) => <Input id={fid} type="number" min="0" dir="ltr" value={form.warranty_months} onChange={(e) => setForm({ ...form, warranty_months: e.target.value })} />}</Field>
                  <div className="sm:col-span-2"><Field label={t("submit.payment_terms")}>{(fid) => <Input id={fid} value={form.payment_terms} onChange={(e) => setForm({ ...form, payment_terms: e.target.value })} placeholder={t("submit.payment_placeholder")} />}</Field></div>
                  <div className="sm:col-span-2"><Field label={t("submit.notes")}>{(fid) => <Textarea id={fid} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />}</Field></div>
                </div>
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold">{t("submit.documents")}</h3>
                  {p.document_requirements.map((req) => (
                    <div key={req.kind} className="rounded-lg border border-line p-3">
                      <Field label={<span className="flex items-center gap-2">{pick(req.names)}{req.required ? <Badge tone="warn">{t("submit.required")}</Badge> : <Badge>{t("submit.optional")}</Badge>}</span>}
                        hint={req.extensions.join(", ")}>
                        {(fid) => (
                          <Input id={fid} type="file" className="h-auto py-1.5" multiple={req.multiple} accept={req.extensions.join(",")}
                            onChange={(e) => setFiles({ ...files, [req.kind]: Array.from(e.target.files ?? []) })} />
                        )}
                      </Field>
                    </div>
                  ))}
                </div>
                {p.content_sealed
                  ? <Alert tone="sealed" title={t("submit.seal_note_title")}>{t(p.opening_mode === "sealed_anytime" ? "submit.seal_note_anytime" : "submit.seal_note_body")}</Alert>
                  : <Alert tone="primary" title={t("submit.visible_note_title")}>{t("submit.visible_note_body")}</Alert>}
                {!confirm ? (
                  <Button size="lg" onClick={() => setConfirm(true)} disabled={!form.price || !form.delivery_days || !form.warranty_months || !requiredOk}>
                    <Upload className="size-5" />{p.content_sealed ? t("submit.submit") : t("submit.submit_plain")}
                  </Button>
                ) : (
                  <div className="space-y-2 rounded-lg bg-primary-soft p-4 text-sm">
                    <p>{t("submit.confirm", { total: agorotToShekels(priceAgorot + vat, locale) })}</p>
                    <div className="flex gap-2">
                      <Button onClick={submit} busy={busy}><Lock className="size-4" />{t("submit.confirm_button")}</Button>
                      <Button variant="ghost" onClick={() => setConfirm(false)}>{t("common.cancel")}</Button>
                    </div>
                  </div>
                )}
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title={t("submit.request")} />
            <div className="space-y-4 p-5 text-sm">
              {p.description && <p className="whitespace-pre-line text-ink-2">{p.description}</p>}
              <KeyValue items={[
                [t("rfq.quantity"), `${p.details.quantity ?? "—"} ${p.details.unit ?? ""}`],
                [t("rfq.deadline"), <span key="d" className="ltr font-medium">{formatDateTime(p.submission_deadline, locale)}</span>],
                [t("rfq.expected_delivery"), p.details.expected_delivery_date ? formatDate(p.details.expected_delivery_date, locale) : "—"],
                [t("process.categories"), p.categories.map((c) => c.path).join(" · ")],
                [t("process.contact"), <span key="c">{p.contact.name}<br /><span className="ltr">{p.contact.email}</span></span>],
              ]} />
              {p.details.technical_specification && <div><div className="mb-1 font-medium">{t("rfq.technical_specification")}</div><p className="whitespace-pre-line rounded-lg bg-surface-2 p-3 text-ink-2">{p.details.technical_specification}</p></div>}
              {p.details.additional_requirements && <div><div className="mb-1 font-medium">{t("rfq.additional_requirements")}</div><p className="whitespace-pre-line text-ink-2">{p.details.additional_requirements}</p></div>}
              {p.documents.length > 0 && (
                <ul className="space-y-1">
                  {p.documents.map((d) => <li key={d.id}><a className="flex items-center gap-2 text-primary hover:underline" href={`/api/v1/processes/${p.id}/documents/${d.id}`}><FileText className="size-4" />{d.title}</a></li>)}
                </ul>
              )}
            </div>
          </Card>
          <Card className="p-5">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="mt-0.5 size-5 text-accent" />
              <div>
                <div className="text-sm font-semibold">{t("submit.fair_title")}</div>
                <p className="mt-1 text-sm text-muted">{t("submit.fair_body")}</p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
