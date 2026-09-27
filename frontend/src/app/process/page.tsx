"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDownUp, CheckCircle2, Eye, CircleDashed, Download, ExternalLink, FileText, KeyRound, Lock, LockOpen, Printer, Send, ShieldCheck, XCircle,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { EventLabel, StatusBadge } from "@/components/EventLabel";
import { Timeline, type Stage } from "@/components/Timeline";
import { AddSupplierModal, OpeningModeBadge } from "@/components/RfqControls";
import {
  Alert, Badge, Button, Card, CardHeader, cx, Empty, ErrorAlert, Field, Input, KeyValue, Modal, PageHeader, Select, Spinner, Stat, Table, Tabs, Textarea,
} from "@/components/ui";
import { useI18n } from "@/i18n/I18nProvider";
import { agorotToShekels, api, ApiError, formatBytes, formatDate, formatDateTime } from "@/lib/api";
import { useQueryParam, useSession } from "@/lib/session";

interface ProcessView {
  id: string; process_type: string; reference_number: string; title: string; description: string; status: string; phase: string;
  details: Record<string, unknown>; submission_deadline: string; opening_time: string; published_at: string | null;
  contact: { name: string; email: string; phone: string };
  categories: { id: string; path: string }[];
  documents: { id: string; kind: string; title: string; filename: string; size_bytes: number; sha256: string }[];
  timeline: Stage[]; vault_status: string | null; server_time: string; opening_mode: string | null; content_sealed: boolean;
  created_by?: string; created_at?: string; recipient_count?: number; sealed_count?: number; my_participation?: string[];
  participants?: { user_id: string; name: string; participation: string }[];
  opening_policy?: { rules: { type: string; params?: Record<string, unknown> }[]; required_approvals: number; frozen: boolean };
  cancelled_reason?: string | null;
  decision?: { decision_type: string; reason: string; supplier_name: string | null; decided_at: string; decided_by: string | null } | null;
  can?: { edit: boolean; open: boolean; read_content: boolean; content_readable_now: boolean; decide: boolean; protocol: boolean;
    monitor: boolean; edit_distribution: boolean };
}

type TabKey = "overview" | "distribution" | "opening" | "evaluation" | "protocols" | "audit";

function Overview({ p }: { p: ProcessView }) {
  const { t, locale } = useI18n();
  const d = p.details as { quantity?: number; unit?: string; technical_specification?: string; expected_delivery_date?: string; additional_requirements?: string };
  return (
    <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr]">
      <Card>
        <CardHeader title={t("process.request_details")} />
        <div className="space-y-3 p-5">
          {p.description && <p className="whitespace-pre-line text-ink-2">{p.description}</p>}
          <KeyValue items={[
            [t("rfq.quantity"), `${d.quantity ?? "—"} ${d.unit ?? ""}`],
            [t("opening_mode.title"), <OpeningModeBadge key="om" mode={p.opening_mode} />],
            [t("process.categories"), <div key="c" className="flex flex-wrap gap-1.5">{p.categories.map((c) => <Badge key={c.id} tone="primary">{c.path}</Badge>)}</div>],
            [t("rfq.deadline"), <span key="d" className="ltr">{formatDateTime(p.submission_deadline, locale)}</span>],
            [t("rfq.expected_delivery"), d.expected_delivery_date ? formatDate(d.expected_delivery_date, locale) : "—"],
            [t("process.created_by"), p.created_by ?? "—"],
          ]} />
          {(d.technical_specification || d.additional_requirements) && (
            <div className={cx("grid gap-4", d.technical_specification && d.additional_requirements && "xl:grid-cols-2")}>
              {d.technical_specification && (
                <div>
                  <h3 className="mb-1 text-sm font-medium">{t("rfq.technical_specification")}</h3>
                  <p className="whitespace-pre-line rounded-lg bg-surface-2 p-3 text-sm text-ink-2">{d.technical_specification}</p>
                </div>
              )}
              {d.additional_requirements && (
                <div>
                  <h3 className="mb-1 text-sm font-medium">{t("rfq.additional_requirements")}</h3>
                  <p className="whitespace-pre-line text-sm text-ink-2">{d.additional_requirements}</p>
                </div>
              )}
            </div>
          )}
        </div>
      </Card>
      <div className="space-y-5">
        <Card>
          <CardHeader title={t("process.documents")} />
          <div className="p-5">
            {p.documents.length === 0 ? <p className="text-sm text-muted">{t("process.no_documents")}</p> : (
              <ul className="space-y-2">
                {p.documents.map((doc) => (
                  <li key={doc.id}>
                    <a href={`/api/v1/processes/${p.id}/documents/${doc.id}`} className="flex items-center gap-2 text-sm text-primary hover:underline">
                      <FileText className="size-4" />{doc.title}<span className="text-xs text-muted">({formatBytes(doc.size_bytes)})</span>
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>
        <Card>
          <CardHeader title={t("process.contact")} />
          <div className="p-5 text-sm">
            <KeyValue items={[[t("rfq.contact_name"), p.contact.name || "—"], [t("rfq.contact_email"), <span key="e" className="ltr">{p.contact.email || "—"}</span>], [t("rfq.contact_phone"), <span key="ph" className="ltr">{p.contact.phone || "—"}</span>]]} />
          </div>
        </Card>
        {p.participants && (
          <Card>
            <CardHeader title={t("process.participants")} subtitle={t("process.participants_hint")} />
            <ul className="divide-y divide-line text-sm">
              {p.participants.map((u) => (
                <li key={u.user_id + u.participation} className="flex items-center justify-between px-5 py-2.5">
                  {u.name}<Badge>{t(`participation.${u.participation}`)}</Badge>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </div>
  );
}

interface Fairness {
  stats: Record<string, number>;
  submitted_revealed: boolean;
  manual_changes_possible: boolean;
  editable_now: boolean;
  excluded_at_publication: { supplier_id: string; company_name: string; reason: string }[];
  snapshots: { id: string; kind: string; created_at: string; recipient_count: number; snapshot_hash: string }[];
  recipients: { supplier_id: string; supplier_name: string; city: string; snapshot_kind: string; match: { relation: string; supplier_category: string; process_category: string }[];
    notified_at: string; delivery_status: string; opened_at: string | null; started: boolean; submitted: boolean | null;
    manual_reason: string | null; removed: boolean; removed_at: string | null; removed_by: string | null; removal_reason: string | null }[];
}

function Distribution({ p }: { p: ProcessView }) {
  const { t, locale } = useI18n();
  const [data, setData] = useState<Fairness | null>(null);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<{ id: string; name: string } | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(() => api.get<Fairness>(`/processes/${p.id}/distribution`).then(setData), [p.id]);
  useEffect(() => { if (p.status !== "DRAFT") void load(); }, [p.status, load]);
  if (p.status === "DRAFT") return <Empty title={t("fairness.not_published")}>{t("fairness.not_published_body")}</Empty>;
  if (!data) return <Spinner />;
  const s = data.stats;
  const editable = data.editable_now && !!p.can?.edit_distribution;

  const add = async (supplierId: string, _name: string, why: string) => {
    setBusy(true); setError(null);
    try { await api.post(`/processes/${p.id}/distribution/recipients`, { supplier_id: supplierId, reason: why }); setAdding(false); await load(); }
    catch (err) { setError(err); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!removing) return;
    setBusy(true); setError(null);
    try { await api.post(`/processes/${p.id}/distribution/recipients/${removing.id}/remove`, { reason }); setRemoving(null); setReason(""); await load(); }
    catch (err) { setError(err); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-6">
      {data.manual_changes_possible ? (
        <Alert tone="primary" title={t("fairness.banner_editable_title")}>{t("fairness.banner_editable_body")}</Alert>
      ) : (
        <Alert tone="success" title={t("fairness.banner_title")}>{t("fairness.banner_body")}</Alert>
      )}
      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-7">
        <Stat label={t("fairness.eligible")} value={s.eligible} tone="primary" />
        <Stat label={t("fairness.notifications")} value={s.notifications} />
        <Stat label={t("fairness.delivered")} value={s.delivered} tone="success" />
        <Stat label={t("fairness.failed")} value={s.failed} tone={s.failed ? "danger" : "neutral"} />
        <Stat label={t("fairness.opened")} value={s.opened} />
        <Stat label={t("fairness.started")} value={s.started} />
        <Stat label={t("fairness.submitted")} value={data.submitted_revealed ? s.submitted : "—"} tone="sealed" />
      </div>
      {(s.manually_added > 0 || s.manually_removed > 0 || data.excluded_at_publication.length > 0) && (
        <Alert tone="warn" title={t("fairness.manual_changes_title")}>
          {t("fairness.manual_changes_body", { added: s.manually_added, removed: s.manually_removed + data.excluded_at_publication.length })}
        </Alert>
      )}
      <Card>
        <CardHeader title={t("fairness.snapshots")} subtitle={t("fairness.snapshots_hint")} />
        <Table>
          <thead><tr><th>{t("fairness.snapshot_kind")}</th><th>{t("fairness.created")}</th><th>{t("fairness.recipients")}</th><th>SHA-256</th></tr></thead>
          <tbody>
            {data.snapshots.map((sn) => (
              <tr key={sn.id}>
                <td><Badge tone={sn.kind === "INITIAL" ? "primary" : sn.kind === "MANUAL" ? "warn" : "neutral"}>{t(`fairness.kind_${sn.kind}`)}</Badge></td>
                <td className="ltr whitespace-nowrap">{formatDateTime(sn.created_at, locale)}</td>
                <td>{sn.recipient_count}</td>
                <td className="hash">{sn.snapshot_hash}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
      {data.excluded_at_publication.length > 0 && (
        <Card>
          <CardHeader title={t("fairness.excluded_title")} />
          <ul className="divide-y divide-line text-sm">
            {data.excluded_at_publication.map((x) => (
              <li key={x.supplier_id} className="px-5 py-2.5"><span className="font-medium">{x.company_name}</span> <span className="text-muted">— {x.reason}</span></li>
            ))}
          </ul>
        </Card>
      )}
      <Card>
        <CardHeader title={t("fairness.recipients_title")} subtitle={data.submitted_revealed ? undefined : t("fairness.submitted_hidden")}
          actions={editable && <Button size="sm" variant="secondary" onClick={() => { setError(null); setAdding(true); }}>{t("distribution_edit.add")}</Button>} />
        <Table>
          <thead><tr><th>{t("fairness.supplier")}</th><th>{t("fairness.match_reason")}</th><th>{t("fairness.delivery")}</th><th>{t("fairness.opened")}</th><th>{t("fairness.started")}</th><th>{t("fairness.submitted")}</th>{editable && <th />}</tr></thead>
          <tbody>
            {data.recipients.map((r) => (
              <tr key={r.supplier_id} className={r.removed ? "bg-surface-2/70" : ""}>
                <td>
                  <div className={cx("font-medium", r.removed && "text-muted line-through")}>{r.supplier_name}</div>
                  <div className="text-xs text-muted">{r.city}{r.snapshot_kind === "SUPPLEMENTAL" && ` · ${t("fairness.kind_SUPPLEMENTAL")}`}</div>
                  {r.removed && <div className="mt-1 text-xs text-danger">{t("distribution_edit.removed_line", { by: r.removed_by ?? "—", at: formatDateTime(r.removed_at, locale) })}: {r.removal_reason}</div>}
                </td>
                <td className="text-xs text-ink-2">
                  {r.match.map((m, i) => <div key={i}>{m.supplier_category} <span className="text-muted">({t(`match.${m.relation}`)})</span></div>)}
                  {r.manual_reason && <div className="text-warn">{t("distribution_edit.added_manually")}: {r.manual_reason}</div>}
                </td>
                <td><Badge tone={r.delivery_status === "SENT" ? "success" : r.delivery_status === "PENDING" ? "primary" : "danger"}>{t(`delivery.${r.delivery_status}`)}</Badge></td>
                <td className="ltr whitespace-nowrap text-xs">{r.opened_at ? formatDateTime(r.opened_at, locale) : "—"}</td>
                <td>{r.started ? <CheckCircle2 className="size-4 text-accent" aria-label={t("common.yes")} /> : <span className="text-muted">—</span>}</td>
                <td>{r.submitted === null ? <Lock className="size-4 text-sealed" aria-label={t("fairness.hidden")} /> : r.submitted ? <CheckCircle2 className="size-4 text-accent" aria-label={t("common.yes")} /> : <span className="text-muted">—</span>}</td>
                {editable && (
                  <td>{!r.removed && !r.submitted && (
                    <Button size="sm" variant="ghost" onClick={() => { setError(null); setReason(""); setRemoving({ id: r.supplier_id, name: r.supplier_name }); }}>{t("distribution_edit.remove")}</Button>
                  )}</td>
                )}
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
      <AddSupplierModal open={adding} onClose={() => setAdding(false)} busy={busy} error={<ErrorAlert error={error} />}
        excludeIds={data.recipients.filter((r) => !r.removed).map((r) => r.supplier_id)} onConfirm={add} />
      <Modal open={!!removing} onClose={() => setRemoving(null)} title={t("distribution_edit.remove_title", { name: removing?.name ?? "" })}
        footer={<><Button variant="ghost" onClick={() => setRemoving(null)}>{t("common.cancel")}</Button>
          <Button variant="danger" onClick={remove} busy={busy} disabled={reason.trim().length < 5}>{t("distribution_edit.remove")}</Button></>}>
        <div className="space-y-4">
          <Alert tone="warn">{t("distribution_edit.remove_note")}</Alert>
          <Field label={t("distribution_edit.reason")} hint={t("distribution_edit.reason_hint")} required>
            {(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <ErrorAlert error={error} />
        </div>
      </Modal>
    </div>
  );
}

interface OpeningStatus {
  vault_status: string | null; opened_at: string | null; sealed_count: number; opening_time: string; phase: string;
  content_sealed: boolean; opening_mode: string | null; submission_deadline: string;
  rules: { type: string }[]; required_approvals: number;
  evaluation_for_you: { satisfied: boolean; results: { rule: string; status: string; code: string; detail: Record<string, unknown> }[] };
  request: { id: string; status: string; requested_at: string; approvals: { approver: string; decision: string; decided_at: string; mfa: boolean }[] } | null;
}

function Opening({ p, reload }: { p: ProcessView; reload: () => void }) {
  const { t, locale } = useI18n();
  const [status, setStatus] = useState<OpeningStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [confirm, setConfirm] = useState(false);
  const [result, setResult] = useState<{ opened_submissions: number; verified_files: number; integrity_failures: unknown[] } | null>(null);
  const load = useCallback(() => api.get<OpeningStatus>(`/processes/${p.id}/opening`).then(setStatus), [p.id]);
  useEffect(() => { void load(); }, [load]);

  if (p.status === "DRAFT") return <Empty title={t("opening.not_published")} />;
  if (!status) return <Spinner />;

  const open = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ status: string; opened_submissions: number; verified_files: number; integrity_failures: unknown[] }>(`/processes/${p.id}/opening/requests`);
      setResult(r);
      setConfirm(false);
      await load();
      reload();
    } catch (err) {
      setError(err);
      setConfirm(false);
      await load();
    } finally {
      setBusy(false);
    }
  };

  if (!status.content_sealed) {
    return (
      <Card className="border-primary/30 p-8 text-center">
        <div className="mx-auto flex size-16 items-center justify-center rounded-full bg-primary-soft text-primary"><Eye className="size-8" /></div>
        <div className="mt-4 text-xl font-semibold">{t("opening.visible_title", { count: status.sealed_count })}</div>
        <p className="mx-auto mt-2 max-w-lg text-sm text-ink-2">{t("opening.visible_body")}</p>
      </Card>
    );
  }
  const sealed = status.vault_status === "SEALED";
  const beforeDeadline = status.phase === "submission_open";
  const icon = (s: string) => s === "PASS" ? <CheckCircle2 className="size-5 text-accent" /> : s === "FAIL" ? <XCircle className="size-5 text-danger" /> : <CircleDashed className="size-5 text-warn" />;
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
      <Card className={cx("overflow-hidden", sealed ? "border-sealed/30" : "border-accent/30")}>
        <div className={cx("flex flex-col items-center px-6 py-12 text-center", sealed ? "bg-sealed-soft" : "bg-accent-soft")}>
          <div className={cx("flex size-28 items-center justify-center rounded-full text-white",
            sealed ? "bg-sealed shadow-[0_16px_40px_rgb(91_63_163/0.3)]" : "bg-accent shadow-[0_16px_40px_rgb(43_116_73/0.3)]")}>
            {sealed ? <Lock className="size-12" strokeWidth={1.8} /> : <LockOpen className="size-12" strokeWidth={1.8} />}
          </div>
          <div className={cx("mt-5 text-4xl font-extrabold", sealed ? "text-sealed" : "text-accent")}>
            {sealed ? t("opening.sealed_count", { count: status.sealed_count }) : t("opening.opened_count", { count: status.sealed_count })}
          </div>
          <p className="mt-3 max-w-md text-base leading-relaxed text-ink-2">{sealed ? t("opening.sealed_body") : t("opening.opened_body", { at: formatDateTime(status.opened_at, locale) })}</p>
          {sealed && <p className="mt-3 text-sm"><span className="text-muted">{t("opening.opening_time")}: </span><span className="ltr font-medium">{formatDateTime(status.opening_time, locale)}</span></p>}
        </div>
        {result && (
          <div className="border-t border-line p-4">
            <Alert tone={result.integrity_failures.length ? "warn" : "success"} title={t("opening.result_title")}>
              {t("opening.result_body", { count: result.opened_submissions, files: result.verified_files, failures: result.integrity_failures.length })}
            </Alert>
          </div>
        )}
      </Card>
      <Card>
        <CardHeader title={t("opening.policy_title")} subtitle={t("opening.policy_hint")} icon={<ShieldCheck className="size-5" />} />
        <ul className="divide-y divide-line">
          {status.evaluation_for_you.results.map((r) => (
            <li key={r.rule} className="flex items-start gap-3 px-5 py-3">
              {sealed ? icon(r.status) : <CheckCircle2 className="size-5 text-accent" />}
              <div>
                <div className="text-sm font-medium">{t(`policy.${r.rule}`)}</div>
                <div className="text-xs text-muted">
                  {t(`policy_code.${r.code}`, { approved: String(r.detail.approved ?? ""), required: String(r.detail.required ?? "") })}
                </div>
              </div>
            </li>
          ))}
        </ul>
        {status.request && (
          <div className="border-t border-line p-5">
            <h3 className="mb-2 text-sm font-medium">{t("opening.approvals")}</h3>
            <ul className="space-y-1 text-sm">
              {status.request.approvals.map((a, i) => (
                <li key={i} className="flex flex-wrap items-center gap-2">
                  <KeyRound className="size-4 text-muted" />{a.approver}
                  <Badge tone={a.decision === "APPROVE" ? "success" : "danger"}>{t(`opening.decision_${a.decision}`)}</Badge>
                  <span className="ltr text-xs text-muted">{formatDateTime(a.decided_at, locale)}</span>
                  {a.mfa && <Badge tone="primary">MFA</Badge>}
                </li>
              ))}
            </ul>
          </div>
        )}
        {sealed && (
          <div className="space-y-3 border-t border-line p-5">
            <ErrorAlert error={error} />
            {p.can?.open ? (
              !confirm ? (
                <Button onClick={() => setConfirm(true)} className="w-full" size="lg" variant={status.phase === "awaiting_opening" ? "primary" : "secondary"}>
                  <LockOpen className="size-5" />{t("opening.open_button")}
                </Button>
              ) : (
                <div className="space-y-2 rounded-lg bg-primary-soft p-3 text-sm">
                  <p>{t("opening.confirm", { count: status.sealed_count })}</p>
                  {beforeDeadline && status.opening_mode === "sealed_anytime" && <p className="font-medium text-warn">{t("opening.early_confirm")}</p>}
                  <div className="flex gap-2">
                    <Button onClick={open} busy={busy}>{t("opening.confirm_button")}</Button>
                    <Button variant="ghost" onClick={() => setConfirm(false)}>{t("common.cancel")}</Button>
                  </div>
                </div>
              )
            ) : <p className="text-sm text-muted">{t("opening.no_permission")}</p>}
            {beforeDeadline && p.can?.open && (
              <p className="text-xs text-muted">{status.opening_mode === "sealed_anytime" ? t("opening.early_allowed") : t("opening.early_warning")}</p>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}

interface ComparisonRow {
  submission_id: string; receipt_number: string; supplier: { id: string; name: string; company_number: string }; submitted_at: string; version_no: number;
  values: { price_before_vat_agorot: number; vat_agorot: number; total_agorot: number; delivery_days: number; warranty_months: number; payment_terms: string; notes: string } | null;
  integrity_ok: boolean; documents: { id: string; kind: string; filename: string; size_bytes: number; sha256: string; integrity: string }[];
  required_documents: { complete: boolean; missing: string[] }; certificates: { count: number; expired: number };
}

type SortKey = "submitted" | "price" | "total" | "delivery" | "warranty";

function SortHeader({ k, sort, onSort, children }: { k: SortKey; sort: SortKey; onSort: (k: SortKey) => void; children: React.ReactNode }) {
  return (
    <th aria-sort={sort === k ? "ascending" : undefined}>
      <button onClick={() => onSort(k)} className={cx("inline-flex items-center gap-1", sort === k && "text-primary")}>
        {children}<ArrowDownUp className="size-3" aria-hidden />
      </button>
    </th>
  );
}

function Evaluation({ p, reload }: { p: ProcessView; reload: () => void }) {
  const { t, locale } = useI18n();
  const [rows, setRows] = useState<ComparisonRow[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [sort, setSort] = useState<SortKey>("submitted");
  const [decisionOpen, setDecisionOpen] = useState(false);
  const [decision, setDecision] = useState({ decision_type: "AWARD", selected_submission_id: "", reason: "" });
  const [saving, setSaving] = useState(false);
  const [decisionError, setDecisionError] = useState<unknown>(null);

  useEffect(() => {
    if (!p.can?.content_readable_now || !p.can?.read_content) return;
    api.get<{ rows: ComparisonRow[] }>(`/processes/${p.id}/comparison`).then((r) => setRows(r.rows)).catch(setError);
  }, [p.id, p.can?.content_readable_now, p.can?.read_content]);

  const sorted = useMemo(() => {
    if (!rows) return null;
    const key = (r: ComparisonRow): number | string => {
      const v = r.values;
      switch (sort) {
        case "price": return v?.price_before_vat_agorot ?? Infinity;
        case "total": return v?.total_agorot ?? Infinity;
        case "delivery": return v?.delivery_days ?? Infinity;
        case "warranty": return -(v?.warranty_months ?? -Infinity);
        default: return r.submitted_at;
      }
    };
    return [...rows].sort((a, b) => (key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0));
  }, [rows, sort]);

  if (!p.can?.content_readable_now) {
    return <Empty title={t("evaluation.sealed_title")}>{t("evaluation.sealed_body")}</Empty>;
  }
  if (!p.can?.read_content) return <Alert tone="warn" title={t("evaluation.no_access")}>{t("evaluation.no_access_body")}</Alert>;
  if (error) return <ErrorAlert error={error} />;
  if (!sorted) return <Spinner />;

  const saveDecision = async () => {
    setSaving(true);
    setDecisionError(null);
    try {
      await api.post(`/processes/${p.id}/decision`, {
        decision_type: decision.decision_type,
        selected_submission_id: decision.decision_type === "AWARD" ? decision.selected_submission_id || null : null,
        reason: decision.reason,
      });
      setDecisionOpen(false);
      reload();
    } catch (err) {
      setDecisionError(err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <Alert tone="primary" title={t("evaluation.no_winner_title")}>{t("evaluation.no_winner_body")}</Alert>
      {!p.content_sealed && p.status === "PUBLISHED" && <Alert tone="warn">{t("evaluation.live_note")}</Alert>}
      <Card>
        <CardHeader title={t("evaluation.comparison")} subtitle={t("evaluation.comparison_hint", { count: sorted.length })}
          actions={p.can?.decide && !p.decision && <Button onClick={() => setDecisionOpen(true)}>{t("evaluation.record_decision")}</Button>} />
        <Table>
          <thead>
            <tr>
              <th>{t("evaluation.supplier")}</th>
              <SortHeader k="price" sort={sort} onSort={setSort}>{t("evaluation.price")}</SortHeader>
              <th>{t("evaluation.vat")}</th>
              <SortHeader k="total" sort={sort} onSort={setSort}>{t("evaluation.total")}</SortHeader>
              <SortHeader k="delivery" sort={sort} onSort={setSort}>{t("evaluation.delivery")}</SortHeader>
              <SortHeader k="warranty" sort={sort} onSort={setSort}>{t("evaluation.warranty")}</SortHeader>
              <th>{t("evaluation.payment")}</th>
              <th>{t("evaluation.documents")}</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.submission_id} className={cx(p.decision?.supplier_name === r.supplier.name && "bg-accent-soft/60")}>
                <td>
                  <div className="font-medium">{r.supplier.name}</div>
                  <div className="ltr text-xs text-muted" style={{ textAlign: "start" }}>{r.receipt_number}</div>
                  <div className="ltr text-xs text-muted" style={{ textAlign: "start" }}>{formatDateTime(r.submitted_at, locale)}</div>
                </td>
                <td className="ltr whitespace-nowrap">{agorotToShekels(r.values?.price_before_vat_agorot, locale)}</td>
                <td className="ltr whitespace-nowrap text-muted">{agorotToShekels(r.values?.vat_agorot, locale)}</td>
                <td className="ltr whitespace-nowrap font-medium">{agorotToShekels(r.values?.total_agorot, locale)}</td>
                <td className="whitespace-nowrap">{r.values ? t("evaluation.days", { n: r.values.delivery_days }) : "—"}</td>
                <td className="whitespace-nowrap">{r.values ? t("evaluation.months", { n: r.values.warranty_months }) : "—"}</td>
                <td className="text-xs">{r.values?.payment_terms || "—"}</td>
                <td>
                  <div className="mb-1 flex flex-wrap gap-1">
                    {r.required_documents.complete ? <Badge tone="success">{t("evaluation.docs_complete")}</Badge> : <Badge tone="warn">{t("evaluation.docs_missing")}</Badge>}
                    {!r.integrity_ok && <Badge tone="danger">{t("evaluation.integrity_failed")}</Badge>}
                    {r.certificates.expired > 0 && <Badge tone="warn">{t("evaluation.cert_expired")}</Badge>}
                  </div>
                  <ul className="space-y-0.5">
                    {r.documents.map((doc) => (
                      <li key={doc.id}>
                        {doc.integrity === "FAILED" ? (
                          <span className="flex items-center gap-1 text-xs text-danger"><XCircle className="size-3" />{doc.filename}</span>
                        ) : (
                          <a href={`/api/v1/submissions/${r.submission_id}/documents/${doc.id}`} className="flex items-center gap-1 text-xs text-primary hover:underline" title={doc.sha256}>
                            <Download className="size-3" />{t(`docs.${doc.kind}`)} · {formatBytes(doc.size_bytes)}
                          </a>
                        )}
                      </li>
                    ))}
                  </ul>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>

      {p.decision && (
        <Card className="border-accent/30">
          <CardHeader title={t("evaluation.decision_recorded")} icon={<CheckCircle2 className="size-5 text-accent" />} />
          <div className="p-5">
            <KeyValue items={[
              [t("evaluation.decision_type"), t(`evaluation.type_${p.decision.decision_type}`)],
              [t("evaluation.selected"), p.decision.supplier_name ?? "—"],
              [t("evaluation.reason"), <span key="r" className="whitespace-pre-line">{p.decision.reason}</span>],
              [t("evaluation.decided_by"), p.decision.decided_by ?? "—"],
              [t("evaluation.decided_at"), <span key="a" className="ltr">{formatDateTime(p.decision.decided_at, locale)}</span>],
            ]} />
          </div>
        </Card>
      )}

      <Modal open={decisionOpen} onClose={() => setDecisionOpen(false)} title={t("evaluation.record_decision")}
        footer={<>
          <Button variant="ghost" onClick={() => setDecisionOpen(false)}>{t("common.cancel")}</Button>
          <Button onClick={saveDecision} busy={saving} disabled={decision.reason.trim().length < 10 || (decision.decision_type === "AWARD" && !decision.selected_submission_id)}>{t("evaluation.save_decision")}</Button>
        </>}>
        <div className="space-y-4">
          <Alert tone="primary">{t("evaluation.decision_note")}</Alert>
          <Field label={t("evaluation.decision_type")}>
            {(id) => (
              <Select id={id} value={decision.decision_type} onChange={(e) => setDecision({ ...decision, decision_type: e.target.value })}>
                <option value="AWARD">{t("evaluation.type_AWARD")}</option>
                <option value="NO_AWARD">{t("evaluation.type_NO_AWARD")}</option>
              </Select>
            )}
          </Field>
          {decision.decision_type === "AWARD" && (
            <Field label={t("evaluation.selected")} required>
              {(id) => (
                <Select id={id} value={decision.selected_submission_id} onChange={(e) => setDecision({ ...decision, selected_submission_id: e.target.value })}>
                  <option value="">{t("evaluation.choose_supplier")}</option>
                  {rows?.filter((r) => r.integrity_ok).map((r) => <option key={r.submission_id} value={r.submission_id}>{r.supplier.name}</option>)}
                </Select>
              )}
            </Field>
          )}
          <Field label={t("evaluation.reason")} hint={t("evaluation.reason_hint")} required>
            {(id) => <Textarea id={id} rows={4} value={decision.reason} onChange={(e) => setDecision({ ...decision, reason: e.target.value })} />}
          </Field>
          <ErrorAlert error={decisionError} />
        </div>
      </Modal>
    </div>
  );
}

interface ProtocolRow { id: string; protocol_type: string; locale: string; content_hash: string; audit_head_hash: string; generated_at: string; generated_by: string | null }

function Protocols({ p, reload }: { p: ProcessView; reload: () => void }) {
  const { t, locale } = useI18n();
  const [rows, setRows] = useState<ProtocolRow[] | null>(null);
  const [lang, setLang] = useState(locale);
  const [busy, setBusy] = useState<string>("");
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(() => api.get<ProtocolRow[]>(`/processes/${p.id}/protocols`).then(setRows).catch(setError), [p.id]);
  useEffect(() => { void load(); }, [load]);

  const generate = async () => {
    setBusy("generate");
    setError(null);
    try {
      await api.post(`/processes/${p.id}/protocols`, { locale: lang });
      await load();
    } catch (err) { setError(err); } finally { setBusy(""); }
  };
  const close = async () => {
    setBusy("close");
    setError(null);
    try { await api.post(`/processes/${p.id}/close`); reload(); } catch (err) { setError(err); } finally { setBusy(""); }
  };

  const available = !!p.can?.content_readable_now && !["DRAFT", "CANCELLED"].includes(p.status);
  return (
    <div className="space-y-6">
      <ErrorAlert error={error} />
      {available && p.can?.protocol && (
        <Card className="flex flex-wrap items-end gap-3 p-5">
          <Field label={t("protocols.language")}>
            {(id) => (
              <Select id={id} value={lang} onChange={(e) => setLang(e.target.value as typeof lang)} className="w-40">
                <option value="he">עברית</option><option value="ar">العربية</option><option value="en">English</option>
              </Select>
            )}
          </Field>
          <Button onClick={generate} busy={busy === "generate"}><Printer className="size-4" />{t("protocols.generate")}</Button>
          {p.status === "DECIDED" && <Button variant="success" onClick={close} busy={busy === "close"}>{t("protocols.close_process")}</Button>}
          <p className="basis-full text-xs text-muted">{t("protocols.hint")}</p>
        </Card>
      )}
      {!available && <Empty title={t("protocols.not_yet")} />}
      {rows && rows.length > 0 && (
        <Card>
          <Table>
            <thead><tr><th>{t("protocols.type")}</th><th>{t("protocols.language")}</th><th>{t("protocols.generated")}</th><th>{t("protocols.fingerprint")}</th><th /></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{t(`protocols.type_${r.protocol_type}`)}</td>
                  <td>{r.locale.toUpperCase()}</td>
                  <td className="whitespace-nowrap"><span className="ltr">{formatDateTime(r.generated_at, locale)}</span><div className="text-xs text-muted">{r.generated_by}</div></td>
                  <td className="hash max-w-60">{r.content_hash}</td>
                  <td><a href={`/api/v1/protocols/${r.id}/html`} target="_blank" rel="noopener" className="inline-flex items-center gap-1 text-sm text-primary hover:underline"><ExternalLink className="size-4" />{t("protocols.open")}</a></td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      )}
    </div>
  );
}

interface AuditItem { sequence: number; event_type: string; severity: string; occurred_at: string; actor: string | null; actor_role: string | null; ip: string | null; event_hash: string; metadata: Record<string, unknown> }

function ProcessAudit({ p }: { p: ProcessView }) {
  const { t, locale } = useI18n();
  const [items, setItems] = useState<AuditItem[] | null>(null);
  useEffect(() => { api.get<{ items: AuditItem[] }>(`/audit/events?process_id=${p.id}&limit=300`).then((r) => setItems(r.items)); }, [p.id]);
  if (!items) return <Spinner />;
  return (
    <Card>
      <Table>
        <thead><tr><th>#</th><th>{t("audit.time")}</th><th>{t("audit.event")}</th><th>{t("audit.actor")}</th><th>{t("audit.hash")}</th></tr></thead>
        <tbody>
          {items.map((e) => (
            <tr key={e.sequence}>
              <td className="text-muted">{e.sequence}</td>
              <td className="ltr whitespace-nowrap text-xs">{formatDateTime(e.occurred_at, locale)}</td>
              <td><EventLabel type={e.event_type} severity={e.severity} /></td>
              <td className="text-xs">{e.actor ?? (e.actor_role ? t(`roles.${e.actor_role}`) : t("common.system"))}</td>
              <td className="hash max-w-48 text-muted">{e.event_hash.slice(0, 16)}…</td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}

export default function ProcessPage() {
  const { t } = useI18n();
  const { can } = useSession();
  const id = useQueryParam("id");
  const [p, setP] = useState<ProcessView | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tab, setTab] = useState<TabKey>("overview");
  const [publishing, setPublishing] = useState(false);
  const [confirmPublish, setConfirmPublish] = useState(false);

  const load = useCallback(() => {
    if (!id) return;
    api.get<ProcessView>(`/processes/${id}`).then(setP).catch(setError);
  }, [id]);
  useEffect(load, [load]);

  const publish = async () => {
    if (!p) return;
    setPublishing(true);
    setError(null);
    try {
      await api.post(`/processes/${p.id}/publish`, {});
      setConfirmPublish(false);
      load();
      setTab("distribution");
    } catch (err) { setError(err); } finally { setPublishing(false); }
  };

  const tabs: { key: TabKey; label: string; badge?: React.ReactNode }[] = [{ key: "overview", label: t("process.tab_overview") }];
  if (can("process.monitor")) tabs.push({ key: "distribution", label: t("process.tab_distribution"), badge: p?.recipient_count ? <Badge>{p.recipient_count}</Badge> : undefined });
  tabs.push({ key: "opening", label: t("process.tab_opening"), badge: p?.vault_status === "SEALED" ? <Lock className="size-3.5 text-sealed" /> : undefined });
  tabs.push({ key: "evaluation", label: t("process.tab_evaluation") });
  if (can("protocol.read")) tabs.push({ key: "protocols", label: t("process.tab_protocols") });
  if (can("audit.read")) tabs.push({ key: "audit", label: t("process.tab_audit") });

  return (
    <AppShell>
      {error && !p ? <ErrorAlert error={error instanceof ApiError && error.status === 404 ? new ApiError(404, "not_found", "") : error} /> : !p ? <Spinner /> : (
        <>
          <PageHeader
            eyebrow={<span className="flex flex-wrap items-center gap-2"><span className="ltr font-medium text-ink-2">{p.reference_number}</span><span>·</span>{t(`types.${p.process_type}`)}</span>}
            title={p.title}
            actions={<>
              <OpeningModeBadge mode={p.opening_mode} />
              <StatusBadge status={p.status} phase={p.phase} />
              {p.can?.edit && p.status === "DRAFT" && <Button onClick={() => setConfirmPublish(true)}><Send className="size-4 rtl:-scale-x-100" />{t("process.publish")}</Button>}
            </>}
          />
          {error ? <div className="mb-4"><ErrorAlert error={error} /></div> : null}
          {p.status === "CANCELLED" && <div className="mb-4"><Alert tone="danger" title={t("process.cancelled")}>{p.cancelled_reason}</Alert></div>}
          <Card className="mb-5 px-5 py-3"><Timeline stages={p.timeline} /></Card>
          <Tabs tabs={tabs} value={tab} onChange={setTab} />
          <div className="mt-5">
            {tab === "overview" && <Overview p={p} />}
            {tab === "distribution" && <Distribution p={p} />}
            {tab === "opening" && <Opening p={p} reload={load} />}
            {tab === "evaluation" && <Evaluation p={p} reload={load} />}
            {tab === "protocols" && <Protocols p={p} reload={load} />}
            {tab === "audit" && <ProcessAudit p={p} />}
          </div>
          <Modal open={confirmPublish} onClose={() => setConfirmPublish(false)} title={t("process.publish")}
            footer={<><Button variant="ghost" onClick={() => setConfirmPublish(false)}>{t("common.cancel")}</Button><Button onClick={publish} busy={publishing}>{t("new.publish_now")}</Button></>}>
            <p className="text-sm text-ink-2">{t("process.publish_confirm")}</p>
          </Modal>
        </>
      )}
    </AppShell>
  );
}
