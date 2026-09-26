"use client";

import Link from "next/link";
import { Fragment, useEffect, useState } from "react";
import { ShieldCheck, ShieldX } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { EventLabel } from "@/components/EventLabel";
import { Alert, Button, Card, CardHeader, ErrorAlert, PageHeader, Select, Spinner, Table } from "@/components/ui";
import { useI18n } from "@/i18n/I18nProvider";
import { api, formatDateTime } from "@/lib/api";
import { useSession } from "@/lib/session";

interface Item { sequence: number; event_type: string; severity: string; occurred_at: string; actor: string | null; actor_role: string | null; process_id: string | null; process_reference: string | null; ip: string | null; metadata: Record<string, unknown>; previous_hash: string; event_hash: string }
interface Verify { valid: boolean; checked: number; first_broken_sequence: number | null; reason: string | null; head_hash: string }

export default function AuditPage() {
  const { t, locale } = useI18n();
  const { can } = useSession();
  const [items, setItems] = useState<Item[] | null>(null);
  const [severity, setSeverity] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [verify, setVerify] = useState<Verify | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!can("audit.read")) { setItems([]); return; }
    api.get<{ items: Item[] }>(`/audit/events?limit=300${severity ? `&severity=${severity}` : ""}`).then((r) => setItems(r.items)).catch(setError);
  }, [severity, can]);

  const runVerify = async () => {
    setBusy(true); setError(null);
    try { setVerify(await api.post<Verify>("/audit/verify")); } catch (err) { setError(err); } finally { setBusy(false); }
  };

  return (
    <AppShell>
      <PageHeader title={t("audit.title")} subtitle={t("audit.subtitle")}
        actions={can("audit.verify") && <Button onClick={runVerify} busy={busy}><ShieldCheck className="size-4" />{t("audit.verify")}</Button>} />
      <div className="space-y-6">
        <ErrorAlert error={error} />
        {verify && (
          <Alert tone={verify.valid ? "success" : "danger"} title={verify.valid ? t("audit.valid", { count: verify.checked }) : t("audit.broken", { seq: verify.first_broken_sequence ?? "?" })}>
            <span className="flex items-center gap-2">{verify.valid ? <ShieldCheck className="size-4" /> : <ShieldX className="size-4" />}<span className="hash">{verify.head_hash}</span></span>
          </Alert>
        )}
        {can("audit.read") ? (
          <Card>
            <CardHeader title={t("audit.events")} subtitle={t("audit.events_hint")}
              actions={
                <Select value={severity} onChange={(e) => setSeverity(e.target.value)} className="w-44" aria-label={t("audit.severity")}>
                  <option value="">{t("audit.all_severities")}</option>
                  <option value="CRITICAL">{t("audit.critical")}</option>
                  <option value="WARNING">{t("audit.warning")}</option>
                  <option value="INFO">{t("audit.info")}</option>
                </Select>
              } />
            {!items ? <Spinner /> : (
              <Table>
                <thead><tr><th>#</th><th>{t("audit.time")}</th><th>{t("audit.event")}</th><th>{t("audit.process")}</th><th>{t("audit.actor")}</th><th>{t("audit.hash")}</th></tr></thead>
                <tbody>
                  {items.map((e) => (
                    <Fragment key={e.sequence}>
                      <tr className="cursor-pointer hover:bg-surface-2/60" onClick={() => setExpanded(expanded === e.sequence ? null : e.sequence)}>
                        <td className="text-muted">{e.sequence}</td>
                        <td className="ltr whitespace-nowrap text-xs">{formatDateTime(e.occurred_at, locale)}</td>
                        <td><EventLabel type={e.event_type} severity={e.severity} /></td>
                        <td>{e.process_id ? <Link className="ltr text-primary hover:underline" href={`/process/?id=${e.process_id}`} onClick={(ev) => ev.stopPropagation()}>{e.process_reference}</Link> : "—"}</td>
                        <td className="text-xs">{e.actor ?? (e.actor_role ? t(`roles.${e.actor_role}`) : t("common.system"))}</td>
                        <td className="hash text-muted">{e.event_hash.slice(0, 12)}…</td>
                      </tr>
                      {expanded === e.sequence && (
                        <tr><td colSpan={6} className="bg-surface-2">
                          <div className="grid gap-2 text-xs">
                            <div><span className="text-muted">previous_hash </span><span className="hash">{e.previous_hash}</span></div>
                            <div><span className="text-muted">event_hash </span><span className="hash">{e.event_hash}</span></div>
                            {e.ip && <div><span className="text-muted">IP </span><span className="ltr">{e.ip}</span></div>}
                            <pre className="ltr overflow-x-auto rounded bg-surface p-2 text-start" dir="ltr">{JSON.stringify(e.metadata, null, 2)}</pre>
                          </div>
                        </td></tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>
        ) : <Alert tone="primary">{t("audit.verify_only")}</Alert>}
      </div>
    </AppShell>
  );
}
