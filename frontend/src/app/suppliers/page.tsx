"use client";

import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { categoryName, type CategoryNode, useCategories } from "@/components/CategoryPicker";
import { Badge, Card, Empty, Input, PageHeader, Select, Spinner, Table } from "@/components/ui";
import { useI18n } from "@/i18n/I18nProvider";
import { api, formatDate } from "@/lib/api";

interface Row { id: string; company_name: string; company_number: string; city: string; status: string; registered_at: string; category_count: number; categories: string[]; expired_documents: number }

function flatten(nodes: CategoryNode[], acc: CategoryNode[] = []) { for (const n of nodes) { acc.push(n); flatten(n.children, acc); } return acc; }

export default function SuppliersPage() {
  const { t, locale } = useI18n();
  const { tree } = useCategories();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");

  useEffect(() => {
    const handle = setTimeout(() => {
      const params = new URLSearchParams({ limit: "200" });
      if (q) params.set("q", q);
      if (category) params.set("category_id", category);
      api.get<{ items: Row[]; total: number }>(`/suppliers?${params}`).then((r) => { setRows(r.items); setTotal(r.total); });
    }, 200);
    return () => clearTimeout(handle);
  }, [q, category]);

  return (
    <AppShell>
      <PageHeader title={t("registry.title")} subtitle={t("registry.subtitle")} />
      <Card>
        <div className="flex flex-wrap gap-3 border-b border-line p-4">
          <div className="relative min-w-60 flex-1">
            <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("registry.search")} className="ps-9" aria-label={t("registry.search")} />
          </div>
          <Select value={category} onChange={(e) => setCategory(e.target.value)} className="w-72" aria-label={t("registry.category_filter")}>
            <option value="">{t("registry.all_categories")}</option>
            {tree && flatten(tree).map((c) => <option key={c.id} value={c.id}>{"  ".repeat(c.depth)}{categoryName(c, locale)}</option>)}
          </Select>
          <div className="flex items-center text-sm text-muted">{t("registry.count", { count: total })}</div>
        </div>
        {!rows ? <Spinner /> : rows.length === 0 ? <div className="p-6"><Empty title={t("registry.empty")} /></div> : (
          <Table>
            <thead><tr><th>{t("supplier.company_name")}</th><th>{t("supplier.company_number")}</th><th>{t("supplier.city")}</th><th>{t("registry.categories")}</th><th>{t("registry.registered")}</th><th>{t("registry.status")}</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="font-medium">{r.company_name}</td>
                  <td className="ltr" style={{ textAlign: "start" }}>{r.company_number}</td>
                  <td>{r.city}</td>
                  <td className="text-xs text-ink-2">{r.categories.join(" · ")}</td>
                  <td className="ltr whitespace-nowrap">{formatDate(r.registered_at, locale)}</td>
                  <td className="space-x-1 space-x-reverse">
                    <Badge tone={r.status === "ACTIVE" ? "success" : "warn"}>{t(`supplier_status.${r.status}`)}</Badge>
                    {r.expired_documents > 0 && <Badge tone="danger">{t("registry.expired_docs", { count: r.expired_documents })}</Badge>}
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
