"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertTriangle, Building2, Clock, FileClock, Inbox, Lock, Plus, ShieldAlert, Users } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { EventLabel } from "@/components/EventLabel";
import { Badge, Card, CardHeader, Empty, LinkButton, PageHeader, Spinner, Stat } from "@/components/ui";
import { useI18n } from "@/i18n/I18nProvider";
import { api, formatDateTime } from "@/lib/api";
import { useSession } from "@/lib/session";

interface Dashboard {
  cards: Record<string, number>;
  processes_by_status: Record<string, number>;
  processes_by_type: Record<string, number>;
  participation: { reference: string; invited: number; submitted: number | null }[];
  average_suppliers_reached: number | null;
  average_quotations_received: number | null;
  email_delivery: Record<string, number>;
  recent_activity: { sequence: number; event_type: string; severity: string; occurred_at: string; process_reference: string | null; process_id: string | null; actor: string | null }[];
}

// The chart and the averages in its header both cover the latest requests only.
const PARTICIPATION_ROWS = 6;

function average(values: number[]): number | null {
  if (!values.length) return null;
  return Math.round((values.reduce((a, b) => a + b, 0) / values.length) * 10) / 10;
}
const ACTIVITY_ROWS = 6;

function Participation({ rows }: { rows: Dashboard["participation"] }) {
  const { t } = useI18n();
  const shown = rows.slice(-PARTICIPATION_ROWS);
  const max = Math.max(1, ...shown.map((r) => r.invited));
  if (!rows.length) return <Empty title={t("dashboard.no_rfqs")} />;
  return (
    <div className="space-y-2.5">
      {shown.map((r) => (
        <div key={r.reference} className="grid grid-cols-[110px_1fr] items-center gap-3 text-sm">
          <span className="ltr truncate text-muted" style={{ textAlign: "start" }}>{r.reference}</span>
          <div className="space-y-0.5">
            <div className="flex items-center gap-2">
              <div className="h-2.5 rounded-full bg-primary" style={{ width: `${(r.invited / max) * 100}%` }} />
              <span className="text-xs text-ink-2">{r.invited}</span>
            </div>
            <div className="flex items-center gap-2">
              {r.submitted === null ? (
                <span className="flex items-center gap-1 text-xs text-sealed"><Lock className="size-3" />{t("dashboard.sealed_until_opening")}</span>
              ) : (
                <>
                  <div className="h-2.5 rounded-full bg-accent" style={{ width: `${Math.max(2, (r.submitted / max) * 100)}%` }} />
                  <span className="text-xs text-ink-2">{r.submitted}</span>
                </>
              )}
            </div>
          </div>
        </div>
      ))}
      <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1 text-xs text-muted">
        <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-primary" />{t("dashboard.legend_invited")}</span>
        <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-accent" />{t("dashboard.legend_submitted")}</span>
        {rows.length > shown.length && <span className="ms-auto">{t("dashboard.latest_requests", { count: shown.length })}</span>}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { t, locale } = useI18n();
  const { me, can } = useSession();
  const [data, setData] = useState<Dashboard | null>(null);

  useEffect(() => {
    if (me && can("process.read")) api.get<Dashboard>("/dashboard/staff").then(setData);
  }, [me, can]);

  if (me && !can("process.read")) {
    return (
      <AppShell>
        <PageHeader title={t("dashboard.title_admin")} subtitle={t("dashboard.admin_scope")} />
        <div className="grid gap-4 md:grid-cols-3">
          {can("user.manage") && <LinkButton href="/admin/users/" variant="secondary">{t("nav.users")}</LinkButton>}
          {can("category.manage") && <LinkButton href="/admin/categories/" variant="secondary">{t("nav.categories")}</LinkButton>}
          {can("audit.verify") && <LinkButton href="/audit/" variant="secondary">{t("nav.audit")}</LinkButton>}
        </div>
      </AppShell>
    );
  }

  const shownParticipation = data?.participation.slice(-PARTICIPATION_ROWS) ?? [];
  const avgReached = average(shownParticipation.map((r) => r.invited));
  const avgReceived = average(shownParticipation.flatMap((r) => (r.submitted === null ? [] : [r.submitted])));
  const delivery = data?.email_delivery ?? {};
  const totalMail = Object.values(delivery).reduce((a, b) => a + b, 0);
  return (
    <AppShell>
      <PageHeader
        eyebrow={t("dashboard.greeting", { name: me?.full_name ?? "" })}
        title={t("dashboard.title")}
        actions={can("process.create.rfq") && <LinkButton href="/processes/new/"><Plus className="size-4" />{t("nav.new_process")}</LinkButton>}
      />
      {!data ? <Spinner /> : (
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label={t("dashboard.active_rfqs")} value={data.cards.active_rfqs} icon={<Inbox className="size-5" />} tone="primary" />
            <Stat label={t("dashboard.waiting_for_opening")} value={data.cards.waiting_for_opening} icon={<Lock className="size-5" />} tone="sealed" />
            <Stat label={t("dashboard.submissions_today")} value={data.cards.submissions_today} icon={<FileClock className="size-5" />} />
            <Stat label={t("dashboard.registered_suppliers")} value={data.cards.registered_suppliers} icon={<Building2 className="size-5" />} tone="success" />
            <Stat label={t("dashboard.waiting_for_my_approval")} value={data.cards.waiting_for_my_approval} icon={<Clock className="size-5" />} />
            <Stat label={t("dashboard.active_tenders")} value={data.cards.active_tenders} hint={t("dashboard.coming_phase", { phase: 7 })} icon={<Users className="size-5" />} />
            <Stat label={t("dashboard.expiring_documents")} value={data.cards.expiring_supplier_documents} hint={t("dashboard.within_30_days")} icon={<AlertTriangle className="size-5" />} tone="warn" />
            <Stat label={t("dashboard.security_alerts")} value={data.cards.security_alerts_30d} hint={t("dashboard.last_30_days")} icon={<ShieldAlert className="size-5" />} tone={data.cards.security_alerts_30d ? "danger" : "neutral"} />
          </div>

          {/* Side by side rather than stacked: three columns on wide screens, two below that. */}
          <div className="grid gap-5 xl:grid-cols-2 2xl:grid-cols-[1.15fr_1fr_0.85fr]">
            <Card>
              <CardHeader title={t("dashboard.participation")} subtitle={t("dashboard.participation_hint")}
                actions={
                  <div className="flex gap-4 text-sm">
                    <div><div className="text-xs text-muted">{t("dashboard.avg_reached")}</div><div className="font-semibold">{avgReached ?? "—"}</div></div>
                    <div><div className="text-xs text-muted">{t("dashboard.avg_received")}</div><div className="font-semibold">{avgReceived ?? "—"}</div></div>
                  </div>
                } />
              <div className="px-5 py-4"><Participation rows={data.participation} /></div>
            </Card>

            <Card>
              <CardHeader title={t("dashboard.recent_activity")} />
              <ul className="divide-y divide-line">
                {data.recent_activity.slice(0, ACTIVITY_ROWS).map((e) => (
                  <li key={e.sequence} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-5 py-2 text-sm">
                    <EventLabel type={e.event_type} severity={e.severity} />
                    {e.process_id && <Link href={`/process/?id=${e.process_id}`} className="ltr text-primary hover:underline">{e.process_reference}</Link>}
                    <span className="basis-full text-xs text-muted">
                      <span className="ltr">{formatDateTime(e.occurred_at, locale)}</span> · {e.actor ?? t("common.system")}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>

            <div className="grid content-start gap-5 md:grid-cols-2 xl:col-span-2 2xl:col-span-1 2xl:grid-cols-1">
              <Card>
                <CardHeader title={t("dashboard.by_status")} />
                <div className="flex flex-wrap gap-2 px-5 py-4">
                  {Object.entries(data.processes_by_status).map(([status, count]) => (
                    <Badge key={status} tone="neutral">{t(`status.${status}`)} · {count}</Badge>
                  ))}
                </div>
              </Card>
              <Card>
                <CardHeader title={t("dashboard.delivery")} subtitle={t("dashboard.measured")} />
                <div className="space-y-2 px-5 py-4 text-sm">
                  {totalMail === 0 ? <span className="text-muted">—</span> : Object.entries(delivery).map(([status, n]) => (
                    <div key={status} className="flex items-center gap-3">
                      <span className="w-20 text-muted">{t(`delivery.${status}`)}</span>
                      <div className="h-2 flex-1 rounded-full bg-surface-2">
                        <div className={`h-2 rounded-full ${status === "SENT" ? "bg-accent" : status === "PENDING" ? "bg-primary" : "bg-danger"}`} style={{ width: `${(n / totalMail) * 100}%` }} />
                      </div>
                      <span className="w-10 text-end">{n}</span>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
