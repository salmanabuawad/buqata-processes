"use client";

import { useCallback, useEffect, useState } from "react";
import { Pencil, Plus, Search } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { categoryName, CategoryPicker, type CategoryNode, useCategories } from "@/components/CategoryPicker";
import {
  Alert, Badge, Button, Card, Empty, ErrorAlert, Field, Input, Modal, PageHeader, Select, Spinner, Table, Textarea,
} from "@/components/ui";
import { useI18n } from "@/i18n/I18nProvider";
import { api, formatDate } from "@/lib/api";
import { useSession } from "@/lib/session";

interface Row { id: string; company_name: string; company_number: string; city: string; status: string; registered_at: string; category_count: number; categories: string[]; expired_documents: number }
interface Detail {
  id: string; company_name: string; company_number: string; contact_name: string; email: string; phone: string;
  address: string; city: string; website: string; description: string; status: string; categories: { id: string }[];
}

const STATUSES = ["ACTIVE", "INACTIVE", "SUSPENDED", "ARCHIVED"] as const;
const EMPTY_FORM = {
  company_name: "", company_number: "", contact_name: "", email: "", phone: "", password: "",
  address: "", city: "", website: "", description: "",
};

function flatten(nodes: CategoryNode[], acc: CategoryNode[] = []) { for (const n of nodes) { acc.push(n); flatten(n.children, acc); } return acc; }

// Add a supplier (id null) or edit one. Only the administrator reaches this.
function SupplierEditor({ id, onClose, onSaved }: { id: string | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const [form, setForm] = useState(EMPTY_FORM);
  const [categories, setCategories] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(id === null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!id) return;
    api.get<Detail>(`/suppliers/${id}`).then((s) => {
      setForm({ company_name: s.company_name, company_number: s.company_number, contact_name: s.contact_name,
        email: s.email, phone: s.phone, password: "", address: s.address, city: s.city, website: s.website,
        description: s.description });
      setCategories(s.categories.map((c) => c.id));
      setLoaded(true);
    }).catch(setError);
  }, [id]);

  const set = (key: keyof typeof EMPTY_FORM) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (id) {
        const changes: Partial<typeof form> = { ...form };
        delete changes.email;
        delete changes.password;
        await api.patch(`/suppliers/${id}`, { ...changes, category_ids: categories });
      } else {
        await api.post("/suppliers", { ...form, category_ids: categories });
      }
      onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open onClose={onClose} title={id ? t("registry.edit_title") : t("registry.new_title")}
      footer={<>
        <Button variant="secondary" type="button" onClick={onClose}>{t("common.cancel")}</Button>
        <Button type="submit" form="supplier-editor" busy={busy} disabled={!loaded || categories.length === 0}>{t("common.save")}</Button>
      </>}>
      {!loaded && !error ? <Spinner /> : (
        <form id="supplier-editor" onSubmit={save} className="space-y-4">
          <ErrorAlert error={error} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("supplier.company_name")} required>{(fid) => <Input id={fid} required minLength={2} value={form.company_name} onChange={set("company_name")} />}</Field>
            <Field label={t("supplier.company_number")} required>{(fid) => <Input id={fid} required pattern="\d{8,9}" inputMode="numeric" dir="ltr" value={form.company_number} onChange={set("company_number")} />}</Field>
            <Field label={t("supplier.contact_name")} required>{(fid) => <Input id={fid} required minLength={2} value={form.contact_name} onChange={set("contact_name")} />}</Field>
            <Field label={t("supplier.phone")} required>{(fid) => <Input id={fid} required minLength={7} type="tel" dir="ltr" value={form.phone} onChange={set("phone")} />}</Field>
            <Field label={t("auth.email")} hint={id ? t("registry.email_fixed") : undefined} required>
              {(fid) => <Input id={fid} required type="email" dir="ltr" autoComplete="off" value={form.email} onChange={set("email")} disabled={!!id} />}
            </Field>
            {!id && (
              <Field label={t("auth.password")} hint={t("registry.password_hint")} required>
                {(fid) => <Input id={fid} required type="password" minLength={10} dir="ltr" autoComplete="new-password" value={form.password} onChange={set("password")} />}
              </Field>
            )}
            <Field label={t("supplier.address")}>{(fid) => <Input id={fid} value={form.address} onChange={set("address")} />}</Field>
            <Field label={t("supplier.city")}>{(fid) => <Input id={fid} value={form.city} onChange={set("city")} />}</Field>
            <div className="sm:col-span-2"><Field label={t("supplier.website")}>{(fid) => <Input id={fid} type="url" dir="ltr" placeholder="https://" value={form.website} onChange={set("website")} />}</Field></div>
            <div className="sm:col-span-2"><Field label={t("supplier.description")}>{(fid) => <Textarea id={fid} value={form.description} onChange={set("description")} />}</Field></div>
          </div>
          <div className="space-y-2">
            <h3 className="font-medium">{t("register.categories")}</h3>
            <CategoryPicker value={categories} onChange={setCategories} />
          </div>
        </form>
      )}
    </Modal>
  );
}

function StatusEditor({ row, onClose, onSaved }: { row: Row; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const [status, setStatus] = useState(row.status === "ARCHIVED" ? "ACTIVE" : "ARCHIVED");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.patch(`/suppliers/${row.id}/status`, { status, reason });
      onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open onClose={onClose} title={`${t("registry.status_title")} — ${row.company_name}`}
      footer={<>
        <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
        <Button variant={status === "ARCHIVED" ? "danger" : "primary"} busy={busy}
          disabled={status === row.status || reason.trim().length < 5} onClick={save}>{t("common.save")}</Button>
      </>}>
      <div className="space-y-4">
        <ErrorAlert error={error} />
        <Field label={t("registry.new_status")}>
          {(fid) => (
            <Select id={fid} value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUSES.map((s) => <option key={s} value={s}>{t(`supplier_status.${s}`)}</option>)}
            </Select>
          )}
        </Field>
        {status === "ARCHIVED" && <Alert tone="warn">{t("registry.archive_hint")}</Alert>}
        <Field label={t("users.reason")} hint={t("users.reason_hint")} required>
          {(fid) => <Input id={fid} required minLength={5} value={reason} onChange={(e) => setReason(e.target.value)} />}
        </Field>
      </div>
    </Modal>
  );
}

export default function SuppliersPage() {
  const { t, locale } = useI18n();
  const { can } = useSession();
  const manage = can("supplier.registry.manage");
  const { tree } = useCategories();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [editing, setEditing] = useState<string | null | undefined>(undefined);
  const [statusRow, setStatusRow] = useState<Row | null>(null);
  const [saved, setSaved] = useState(false);
  const [version, setVersion] = useState(0);

  const reload = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    const handle = setTimeout(() => {
      const params = new URLSearchParams({ limit: "200" });
      if (q) params.set("q", q);
      if (category) params.set("category_id", category);
      if (status) params.set("status", status);
      api.get<{ items: Row[]; total: number }>(`/suppliers?${params}`).then((r) => { setRows(r.items); setTotal(r.total); });
    }, 200);
    return () => clearTimeout(handle);
  }, [q, category, status, version]);

  const afterSave = () => { setEditing(undefined); setStatusRow(null); setSaved(true); reload(); };

  return (
    <AppShell>
      <PageHeader title={t("registry.title")} subtitle={t("registry.subtitle")}
        actions={manage && <Button onClick={() => { setSaved(false); setEditing(null); }}><Plus className="size-4" />{t("registry.add")}</Button>} />
      {saved && <div className="mb-4"><Alert tone="success">{t("registry.saved")}</Alert></div>}
      <Card>
        <div className="flex flex-wrap gap-3 border-b border-line p-4">
          <div className="relative min-w-60 flex-1">
            <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("registry.search")} className="ps-9" aria-label={t("registry.search")} />
          </div>
          <Select value={category} onChange={(e) => setCategory(e.target.value)} className="w-72" aria-label={t("registry.category_filter")}>
            <option value="">{t("registry.all_categories")}</option>
            {tree && flatten(tree).map((c) => <option key={c.id} value={c.id}>{"  ".repeat(c.depth)}{categoryName(c, locale)}</option>)}
          </Select>
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-56" aria-label={t("registry.status_filter")}>
            <option value="">{t("registry.all_but_archived")}</option>
            {STATUSES.map((s) => <option key={s} value={s}>{t(`supplier_status.${s}`)}</option>)}
          </Select>
          <div className="flex items-center text-sm text-muted">{t("registry.count", { count: total })}</div>
        </div>
        {!rows ? <Spinner /> : rows.length === 0 ? <div className="p-6"><Empty title={t("registry.empty")} /></div> : (
          <Table>
            <thead><tr><th>{t("supplier.company_name")}</th><th>{t("supplier.company_number")}</th><th>{t("supplier.city")}</th><th>{t("registry.categories")}</th><th>{t("registry.registered")}</th><th>{t("registry.status")}</th>{manage && <th>{t("registry.actions")}</th>}</tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="font-medium">{r.company_name}</td>
                  <td className="ltr" style={{ textAlign: "start" }}>{r.company_number}</td>
                  <td>{r.city}</td>
                  <td className="text-xs text-ink-2">{r.categories.join(" · ")}</td>
                  <td className="ltr whitespace-nowrap">{formatDate(r.registered_at, locale)}</td>
                  <td className="space-x-1 space-x-reverse">
                    <Badge tone={r.status === "ACTIVE" ? "success" : r.status === "ARCHIVED" ? "neutral" : "warn"}>{t(`supplier_status.${r.status}`)}</Badge>
                    {r.expired_documents > 0 && <Badge tone="danger">{t("registry.expired_docs", { count: r.expired_documents })}</Badge>}
                  </td>
                  {manage && (
                    <td className="whitespace-nowrap">
                      <div className="flex gap-1">
                        <Button size="sm" variant="ghost" onClick={() => { setSaved(false); setEditing(r.id); }} aria-label={`${t("common.edit")} ${r.company_name}`}>
                          <Pencil className="size-3.5" />{t("common.edit")}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => { setSaved(false); setStatusRow(r); }}>{t("registry.change_status")}</Button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      {editing !== undefined && <SupplierEditor id={editing} onClose={() => setEditing(undefined)} onSaved={afterSave} />}
      {statusRow && <StatusEditor row={statusRow} onClose={() => setStatusRow(null)} onSaved={afterSave} />}
    </AppShell>
  );
}
