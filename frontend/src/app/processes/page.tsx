"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Lock, Plus, Search } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/EventLabel";
import { Card, Empty, Input, LinkButton, PageHeader, Select, Spinner, Table } from "@/components/ui";
import { useI18n } from "@/i18n/I18nProvider";
import { api, formatDateTime } from "@/lib/api";
import { useSession } from "@/lib/session";

interface Row {
  id: string; process_type: string; reference_number: string; title: string; status: string; phase: string;
  submission_deadline: string; recipient_count: number; sealed_count: number; categories: string[];
}

export default function ProcessesPage() {
  const { t, locale } = useI18n();
  const { can } = useSession();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    const handle = setTimeout(() => {
      const params = new URLSearchParams({ limit: "100" });
      if (q) params.set("q", q);
      if (status) params.set("status", status);
      api.get<{ items: Row[] }>(`/processes?${params}`).then((r) => setRows(r.items));
    }, 200);
    return () => clearTimeout(handle);
  }, [q, status]);

  return (
    <AppShell>
      <PageHeader title={t("processes.title")} subtitle={t("processes.subtitle")}
        actions={can("process.create.rfq") && <LinkButton href="/processes/new/"><Plus className="size-4" />{t("nav.new_process")}</LinkButton>} />
      <Card>
        <div className="flex flex-wrap gap-3 border-b border-line p-4">
          <div className="relative min-w-60 flex-1">
            <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("processes.search")} className="ps-9" aria-label={t("processes.search")} />
          </div>
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-48" aria-label={t("processes.status_filter")}>
            <option value="">{t("processes.all_statuses")}</option>
            {["DRAFT", "PUBLISHED", "OPENED", "DECIDED", "CLOSED", "CANCELLED"].map((s) => <option key={s} value={s}>{t(`status.${s}`)}</option>)}
          </Select>
        </div>
        {!rows ? <Spinner /> : rows.length === 0 ? <div className="p-6"><Empty title={t("processes.empty")} /></div> : (
          <Table>
            <thead>
              <tr>
                <th>{t("processes.reference")}</th><th>{t("processes.name")}</th><th>{t("processes.type")}</th>
                <th>{t("processes.status")}</th><th>{t("processes.deadline")}</th>
                <th>{t("processes.invited")}</th><th>{t("processes.submissions")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="hover:bg-surface-2/60">
                  <td className="ltr whitespace-nowrap" style={{ textAlign: "start" }}><Link href={`/process/?id=${r.id}`} className="font-medium text-primary hover:underline">{r.reference_number}</Link></td>
                  <td>
                    <Link href={`/process/?id=${r.id}`} className="font-medium text-ink hover:underline">{r.title}</Link>
                    <div className="text-xs text-muted">{r.categories.join(" · ")}</div>
                  </td>
                  <td className="whitespace-nowrap">{t(`types.${r.process_type}`)}</td>
                  <td><StatusBadge status={r.status} phase={r.phase} /></td>
                  <td className="whitespace-nowrap text-ink-2"><span className="ltr">{formatDateTime(r.submission_deadline, locale)}</span></td>
                  <td>{r.status === "DRAFT" ? "—" : r.recipient_count}</td>
                  <td>
                    {r.status === "PUBLISHED" ? (
                      <span className="inline-flex items-center gap-1 text-sealed"><Lock className="size-3.5" />{r.sealed_count}</span>
                    ) : r.status === "DRAFT" ? "—" : r.sealed_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </AppShell>
  );
}
