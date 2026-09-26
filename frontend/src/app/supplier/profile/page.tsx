"use client";

import { useCallback, useEffect, useState } from "react";
import { FileText, Plus } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { CategoryPicker } from "@/components/CategoryPicker";
import { Alert, Badge, Button, Card, CardHeader, ErrorAlert, Field, Input, Modal, PageHeader, Spinner, Table, Textarea } from "@/components/ui";
import { useI18n } from "@/i18n/I18nProvider";
import { api, formatDate } from "@/lib/api";

interface Profile {
  id: string; company_name: string; company_number: string; contact_name: string; email: string; phone: string; address: string; city: string;
  website: string; description: string; status: string; notify_email: boolean; notify_in_app: boolean; registered_at: string;
  categories: { id: string; path: string }[];
  documents: { id: string; doc_type: string; title: string; issued_on: string | null; expires_on: string | null; expired: boolean; filename: string }[];
}

export default function SupplierProfilePage() {
  const { t, locale } = useI18n();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [form, setForm] = useState<Partial<Profile>>({});
  const [categories, setCategories] = useState<string[]>([]);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState("");
  const [docOpen, setDocOpen] = useState(false);
  const [doc, setDoc] = useState({ doc_type: "bookkeeping", title: "", issued_on: "", expires_on: "" });
  const [docFile, setDocFile] = useState<File | null>(null);

  const load = useCallback(() => api.get<Profile>("/suppliers/me").then((p) => {
    setProfile(p); setForm(p); setCategories(p.categories.map((c) => c.id));
  }), []);
  useEffect(() => { void load(); }, [load]);

  const saveProfile = async () => {
    setBusy("profile"); setError(null); setSaved(null);
    try {
      const { company_name, contact_name, phone, address, city, website, description, notify_email, notify_in_app } = form;
      await api.patch("/suppliers/me", { company_name, contact_name, phone, address, city, website, description, notify_email, notify_in_app });
      setSaved(t("profile.saved"));
      await load();
    } catch (err) { setError(err); } finally { setBusy(""); }
  };
  const saveCategories = async () => {
    setBusy("categories"); setError(null); setSaved(null);
    try {
      const r = await api.put<{ new_invitations: number }>("/suppliers/me/categories", { category_ids: categories });
      setSaved(r.new_invitations ? t("profile.categories_saved_invites", { count: r.new_invitations }) : t("profile.categories_saved"));
      await load();
    } catch (err) { setError(err); } finally { setBusy(""); }
  };
  const uploadDoc = async () => {
    if (!docFile) return;
    setBusy("doc"); setError(null);
    const fd = new FormData();
    fd.append("meta", JSON.stringify({ doc_type: doc.doc_type, title: doc.title || t(`doc_types.${doc.doc_type}`), issued_on: doc.issued_on || null, expires_on: doc.expires_on || null }));
    fd.append("file", docFile);
    try { await api.form("/suppliers/me/documents", fd); setDocOpen(false); await load(); } catch (err) { setError(err); } finally { setBusy(""); }
  };

  if (!profile) return <AppShell><Spinner /></AppShell>;
  const set = (k: keyof Profile) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });
  return (
    <AppShell>
      <PageHeader title={t("profile.title")} subtitle={t("profile.subtitle")} actions={<Badge tone={profile.status === "ACTIVE" ? "success" : "warn"}>{t(`supplier_status.${profile.status}`)}</Badge>} />
      <div className="space-y-6">
        {saved && <Alert tone="success" title={saved} />}
        <ErrorAlert error={error} />
        <div className="grid gap-6 xl:grid-cols-2">
          <Card>
            <CardHeader title={t("register.company")} actions={<Button size="sm" onClick={saveProfile} busy={busy === "profile"}>{t("common.save")}</Button>} />
            <div className="grid gap-4 p-5 sm:grid-cols-2">
              <Field label={t("supplier.company_name")}>{(id) => <Input id={id} value={form.company_name ?? ""} onChange={set("company_name")} />}</Field>
              <Field label={t("supplier.company_number")} hint={t("profile.number_locked")}>{(id) => <Input id={id} value={profile.company_number} disabled dir="ltr" />}</Field>
              <Field label={t("supplier.contact_name")}>{(id) => <Input id={id} value={form.contact_name ?? ""} onChange={set("contact_name")} />}</Field>
              <Field label={t("supplier.phone")}>{(id) => <Input id={id} value={form.phone ?? ""} onChange={set("phone")} dir="ltr" />}</Field>
              <Field label={t("supplier.address")}>{(id) => <Input id={id} value={form.address ?? ""} onChange={set("address")} />}</Field>
              <Field label={t("supplier.city")}>{(id) => <Input id={id} value={form.city ?? ""} onChange={set("city")} />}</Field>
              <div className="sm:col-span-2"><Field label={t("supplier.website")}>{(id) => <Input id={id} value={form.website ?? ""} onChange={set("website")} dir="ltr" />}</Field></div>
              <div className="sm:col-span-2"><Field label={t("supplier.description")}>{(id) => <Textarea id={id} value={form.description ?? ""} onChange={set("description")} />}</Field></div>
              <fieldset className="space-y-2 sm:col-span-2">
                <legend className="text-sm font-medium">{t("profile.notifications")}</legend>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-[var(--primary)]" checked={!!form.notify_email} onChange={(e) => setForm({ ...form, notify_email: e.target.checked })} />{t("profile.notify_email")}</label>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-[var(--primary)]" checked={!!form.notify_in_app} onChange={(e) => setForm({ ...form, notify_in_app: e.target.checked })} />{t("profile.notify_in_app")}</label>
              </fieldset>
            </div>
          </Card>
          <Card>
            <CardHeader title={t("register.categories")} subtitle={t("profile.categories_hint")} actions={<Button size="sm" onClick={saveCategories} busy={busy === "categories"} disabled={!categories.length}>{t("common.save")}</Button>} />
            <div className="p-5"><CategoryPicker value={categories} onChange={setCategories} max={60} /></div>
          </Card>
        </div>
        <Card>
          <CardHeader title={t("profile.certificates")} subtitle={t("profile.certificates_hint")} actions={<Button size="sm" variant="secondary" onClick={() => setDocOpen(true)}><Plus className="size-4" />{t("profile.add_certificate")}</Button>} />
          {profile.documents.length === 0 ? <p className="p-5 text-sm text-muted">{t("profile.no_certificates")}</p> : (
            <Table>
              <thead><tr><th>{t("profile.doc_title")}</th><th>{t("profile.issued")}</th><th>{t("profile.expires")}</th><th /></tr></thead>
              <tbody>
                {profile.documents.map((d) => (
                  <tr key={d.id}>
                    <td className="flex items-center gap-2"><FileText className="size-4 text-muted" />{d.title}</td>
                    <td className="ltr">{formatDate(d.issued_on, locale)}</td>
                    <td className="ltr">{formatDate(d.expires_on, locale)}</td>
                    <td>{d.expired ? <Badge tone="danger">{t("profile.expired")}</Badge> : <Badge tone="success">{t("profile.valid")}</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      </div>
      <Modal open={docOpen} onClose={() => setDocOpen(false)} title={t("profile.add_certificate")}
        footer={<><Button variant="ghost" onClick={() => setDocOpen(false)}>{t("common.cancel")}</Button><Button onClick={uploadDoc} busy={busy === "doc"} disabled={!docFile}>{t("common.upload")}</Button></>}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("profile.doc_type")}>
            {(id) => (
              <select id={id} className="h-10 w-full rounded-lg border border-line-strong bg-surface px-3" value={doc.doc_type} onChange={(e) => setDoc({ ...doc, doc_type: e.target.value })}>
                {["bookkeeping", "tax_withholding", "insurance", "iso", "other"].map((k) => <option key={k} value={k}>{t(`doc_types.${k}`)}</option>)}
              </select>
            )}
          </Field>
          <Field label={t("profile.doc_title")}>{(id) => <Input id={id} value={doc.title} onChange={(e) => setDoc({ ...doc, title: e.target.value })} />}</Field>
          <Field label={t("profile.issued")}>{(id) => <Input id={id} type="date" dir="ltr" value={doc.issued_on} onChange={(e) => setDoc({ ...doc, issued_on: e.target.value })} />}</Field>
          <Field label={t("profile.expires")}>{(id) => <Input id={id} type="date" dir="ltr" value={doc.expires_on} onChange={(e) => setDoc({ ...doc, expires_on: e.target.value })} />}</Field>
          <div className="sm:col-span-2"><Field label={t("profile.file")} hint="PDF / JPG / PNG">{(id) => <Input id={id} type="file" accept=".pdf,.png,.jpg,.jpeg" className="h-auto py-1.5" onChange={(e) => setDocFile(e.target.files?.[0] ?? null)} />}</Field></div>
        </div>
      </Modal>
    </AppShell>
  );
}
