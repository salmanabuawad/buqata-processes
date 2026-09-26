"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CheckCircle2, Lock } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/EventLabel";
import { Alert, Badge, Card, Empty, PageHeader, Spinner, Table } from "@/components/ui";
import { useI18n } from "@/i18n/I18nProvider";
import { api, formatDateTime } from "@/lib/api";
import { useQueryParam, useSession } from "@/lib/session";

interface Opportunity {
  process_id: string; reference_number: string; title: string; process_type: string; status: string; phase: string;
  deadline: string; invited_at: string; opened_at: string | null; submission_status: string | null; submitted_at: string | null;
}

export default function SupplierHome() {
  const { t, locale } = useI18n();
  const { me } = useSession();
  const welcome = useQueryParam("welcome");
  const [rows, setRows] = useState<Opportunity[] | null>(null);
  useEffect(() => { if (me) api.get<Opportunity[]>("/suppliers/me/opportunities").then(setRows); }, [me]);

  const open = rows?.filter((r) => r.phase === "submission_open") ?? [];
  return (
    <AppShell>
      <PageHeader eyebrow={me?.supplier?.company_name} title={t("supplier_home.title")} subtitle={t("supplier_home.subtitle")} />
      {welcome && <div className="mb-6"><Alert tone="success" title={t("supplier_home.welcome_title")}>{t("supplier_home.welcome_body")}</Alert></div>}
      {!rows ? <Spinner /> : rows.length === 0 ? (
        <Empty title={t("supplier_home.empty")}>{t("supplier_home.empty_body")}</Empty>
      ) : (
        <div className="space-y-6">
          {open.length > 0 && (
            <div className="grid gap-4 md:grid-cols-2">
              {open.map((r) => (
                <Card key={r.process_id} className="p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="ltr text-xs text-muted" style={{ textAlign: "start" }}>{r.reference_number}</div>
                      <Link href={`/supplier/opportunity/?id=${r.process_id}`} className="mt-1 block font-semibold text-ink hover:text-primary">{r.title}</Link>
                    </div>
                    {r.submission_status === "SUBMITTED" ? <Badge tone="success"><CheckCircle2 className="size-3" />{t("supplier_home.submitted")}</Badge> : <Badge tone="primary">{t("supplier_home.open")}</Badge>}
                  </div>
                  <div className="mt-3 text-sm text-ink-2">{t("supplier_home.deadline")}: <span className="ltr font-medium">{formatDateTime(r.deadline, locale)}</span></div>
                  <Link href={`/supplier/opportunity/?id=${r.process_id}`} className="mt-4 inline-flex text-sm font-medium text-primary hover:underline">
                    {r.submission_status === "SUBMITTED" ? t("supplier_home.view_receipt") : t("supplier_home.submit_offer")}
                  </Link>
                </Card>
              ))}
            </div>
          )}
          <Card>
            <Table>
              <thead><tr><th>{t("processes.reference")}</th><th>{t("processes.name")}</th><th>{t("processes.status")}</th><th>{t("processes.deadline")}</th><th>{t("supplier_home.my_submission")}</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.process_id}>
                    <td className="ltr whitespace-nowrap" style={{ textAlign: "start" }}>{r.reference_number}</td>
                    <td><Link href={`/supplier/opportunity/?id=${r.process_id}`} className="font-medium text-primary hover:underline">{r.title}</Link></td>
                    <td><StatusBadge status={r.status} phase={r.phase} /></td>
                    <td className="ltr whitespace-nowrap">{formatDateTime(r.deadline, locale)}</td>
                    <td>
                      {r.submission_status === "SUBMITTED" ? <Badge tone="sealed"><Lock className="size-3" />{t("supplier_home.sealed")}</Badge> :
                        r.submission_status === "OPENED" ? <Badge tone="success">{t("supplier_home.opened")}</Badge> :
                        r.submission_status === "STARTED" ? <Badge>{t("supplier_home.started")}</Badge> : <span className="text-muted">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </div>
      )}
    </AppShell>
  );
}
