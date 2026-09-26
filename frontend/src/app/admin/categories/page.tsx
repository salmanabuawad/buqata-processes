"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { categoryName, type CategoryNode, useCategories } from "@/components/CategoryPicker";
import { Badge, Button, Card, CardHeader, ErrorAlert, Field, Input, Modal, PageHeader, Spinner } from "@/components/ui";
import { useI18n } from "@/i18n/I18nProvider";
import { api } from "@/lib/api";

interface Draft { id?: string; parent_id: string | null; key: string; name_he: string; name_ar: string; name_en: string; is_active?: boolean }

export default function CategoriesAdmin() {
  const { t, locale } = useI18n();
  const { tree, reload } = useCategories(true);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const save = async () => {
    if (!draft) return;
    setBusy(true); setError(null);
    try {
      if (draft.id) await api.patch(`/categories/${draft.id}`, { name_he: draft.name_he, name_ar: draft.name_ar, name_en: draft.name_en, is_active: draft.is_active });
      else await api.post("/categories", { key: draft.key, parent_id: draft.parent_id, name_he: draft.name_he, name_ar: draft.name_ar, name_en: draft.name_en });
      setDraft(null);
      await reload();
    } catch (err) { setError(err); } finally { setBusy(false); }
  };

  const render = (nodes: CategoryNode[]) => (
    <ul className="space-y-1">
      {nodes.map((n) => (
        <li key={n.id}>
          <div className="flex flex-wrap items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-surface-2">
            <span className={n.depth === 0 ? "font-semibold" : ""}>{categoryName(n, locale)}</span>
            <span className="ltr text-xs text-muted">{n.key}</span>
            {!n.is_active && <Badge tone="warn">{t("categories.inactive")}</Badge>}
            {n.direct_suppliers > 0 && <Badge>{t("categories.suppliers", { count: n.direct_suppliers })}</Badge>}
            <span className="ms-auto flex gap-1">
              <Button size="sm" variant="ghost" onClick={() => setDraft({ id: n.id, parent_id: n.parent_id, key: n.key, name_he: n.name_he, name_ar: n.name_ar, name_en: n.name_en, is_active: n.is_active })}>{t("common.edit")}</Button>
              <Button size="sm" variant="ghost" onClick={() => setDraft({ parent_id: n.id, key: `${n.key}.`, name_he: "", name_ar: "", name_en: "" })}><Plus className="size-3.5" />{t("categories.add_child")}</Button>
            </span>
          </div>
          {n.children.length > 0 && <div className="ms-5 border-s border-line ps-3">{render(n.children)}</div>}
        </li>
      ))}
    </ul>
  );

  return (
    <AppShell>
      <PageHeader title={t("categories.title")} subtitle={t("categories.subtitle")}
        actions={<Button onClick={() => setDraft({ parent_id: null, key: "", name_he: "", name_ar: "", name_en: "" })}><Plus className="size-4" />{t("categories.add_root")}</Button>} />
      <Card>
        <CardHeader title={t("categories.tree")} subtitle={t("categories.tree_hint")} />
        <div className="p-4">{tree ? render(tree) : <Spinner />}</div>
      </Card>
      <Modal open={!!draft} onClose={() => setDraft(null)} title={draft?.id ? t("categories.edit") : t("categories.new")}
        footer={<><Button variant="ghost" onClick={() => setDraft(null)}>{t("common.cancel")}</Button><Button onClick={save} busy={busy}>{t("common.save")}</Button></>}>
        {draft && (
          <div className="grid gap-4">
            <ErrorAlert error={error} />
            <Field label={t("categories.key")} hint={t("categories.key_hint")}>{(id) => <Input id={id} dir="ltr" value={draft.key} disabled={!!draft.id} onChange={(e) => setDraft({ ...draft, key: e.target.value })} />}</Field>
            <Field label="עברית" required>{(id) => <Input id={id} dir="rtl" lang="he" value={draft.name_he} onChange={(e) => setDraft({ ...draft, name_he: e.target.value })} />}</Field>
            <Field label="العربية" required>{(id) => <Input id={id} dir="rtl" lang="ar" value={draft.name_ar} onChange={(e) => setDraft({ ...draft, name_ar: e.target.value })} />}</Field>
            <Field label="English" required>{(id) => <Input id={id} dir="ltr" lang="en" value={draft.name_en} onChange={(e) => setDraft({ ...draft, name_en: e.target.value })} />}</Field>
            {draft.id && (
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4" checked={draft.is_active} onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })} />{t("categories.active")}</label>
            )}
          </div>
        )}
      </Modal>
    </AppShell>
  );
}
