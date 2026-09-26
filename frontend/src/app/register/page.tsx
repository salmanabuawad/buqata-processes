"use client";

import { useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { AuthFrame } from "@/components/AuthFrame";
import { CategoryPicker } from "@/components/CategoryPicker";
import { Alert, Button, Card, ErrorAlert, Field, Input, Textarea } from "@/components/ui";
import { useI18n } from "@/i18n/I18nProvider";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";

export default function RegisterPage() {
  const { t, locale } = useI18n();
  const { refresh } = useSession();
  const [form, setForm] = useState({
    company_name: "", company_number: "", contact_name: "", email: "", phone: "", password: "",
    address: "", city: "", website: "", description: "",
  });
  const [categories, setCategories] = useState<string[]>([]);
  const [accept, setAccept] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/suppliers/register", { ...form, category_ids: categories, locale, accept_terms: accept, service_regions: [] });
      await refresh();
      window.location.href = "/supplier/?welcome=1";
    } catch (err) {
      setError(err);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthFrame wide>
      <h1 className="text-2xl font-semibold">{t("register.title")}</h1>
      <p className="mt-1 text-ink-2">{t("register.subtitle")}</p>
      <div className="mt-4"><Alert tone="success" title={t("register.fairness_title")}>{t("register.fairness_body")}</Alert></div>
      <form onSubmit={submit} className="mt-6 space-y-6">
        <ErrorAlert error={error} />
        <Card className="grid gap-4 p-6 sm:grid-cols-2">
          <h2 className="font-semibold sm:col-span-2">{t("register.company")}</h2>
          <Field label={t("supplier.company_name")} required>{(id) => <Input id={id} required minLength={2} value={form.company_name} onChange={set("company_name")} />}</Field>
          <Field label={t("supplier.company_number")} hint={t("register.company_number_hint")} required>{(id) => <Input id={id} required pattern="\d{8,9}" inputMode="numeric" dir="ltr" value={form.company_number} onChange={set("company_number")} />}</Field>
          <Field label={t("supplier.address")}>{(id) => <Input id={id} value={form.address} onChange={set("address")} />}</Field>
          <Field label={t("supplier.city")}>{(id) => <Input id={id} value={form.city} onChange={set("city")} />}</Field>
          <Field label={t("supplier.website")}>{(id) => <Input id={id} type="url" dir="ltr" placeholder="https://" value={form.website} onChange={set("website")} />}</Field>
          <div className="sm:col-span-2"><Field label={t("supplier.description")}>{(id) => <Textarea id={id} value={form.description} onChange={set("description")} />}</Field></div>
        </Card>
        <Card className="grid gap-4 p-6 sm:grid-cols-2">
          <h2 className="font-semibold sm:col-span-2">{t("register.contact")}</h2>
          <Field label={t("supplier.contact_name")} required>{(id) => <Input id={id} required value={form.contact_name} onChange={set("contact_name")} />}</Field>
          <Field label={t("supplier.phone")} required>{(id) => <Input id={id} required type="tel" dir="ltr" value={form.phone} onChange={set("phone")} />}</Field>
          <Field label={t("auth.email")} required>{(id) => <Input id={id} required type="email" dir="ltr" autoComplete="email" value={form.email} onChange={set("email")} />}</Field>
          <Field label={t("auth.password")} hint={t("register.password_hint")} required>{(id) => <Input id={id} required type="password" minLength={10} dir="ltr" autoComplete="new-password" value={form.password} onChange={set("password")} />}</Field>
        </Card>
        <Card className="space-y-3 p-6">
          <h2 className="font-semibold">{t("register.categories")}</h2>
          <p className="text-sm text-muted">{t("register.categories_hint")}</p>
          <CategoryPicker value={categories} onChange={setCategories} max={60} />
        </Card>
        <label className="flex items-start gap-3 text-sm">
          <input type="checkbox" className="mt-1 size-4 accent-[var(--primary)]" checked={accept} onChange={(e) => setAccept(e.target.checked)} required />
          <span>{t("register.terms")}</span>
        </label>
        <Button type="submit" size="lg" busy={busy} disabled={!categories.length || !accept}>
          <CheckCircle2 className="size-5" />{t("register.submit")}
        </Button>
      </form>
    </AuthFrame>
  );
}
