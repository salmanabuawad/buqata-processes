"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronDown, Search } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";
import { api } from "@/lib/api";
import { cx, Input, Spinner } from "./ui";

export interface CategoryNode {
  id: string;
  key: string;
  parent_id: string | null;
  name_he: string;
  name_ar: string;
  name_en: string;
  depth: number;
  is_active: boolean;
  direct_suppliers: number;
  children: CategoryNode[];
}

export function useCategories(includeInactive = false) {
  const [tree, setTree] = useState<CategoryNode[] | null>(null);
  const reload = () => api.get<CategoryNode[]>(`/categories${includeInactive ? "?include_inactive=true" : ""}`).then(setTree);
  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [includeInactive]);
  return { tree, reload };
}

export function categoryName(node: Pick<CategoryNode, "name_he" | "name_ar" | "name_en">, locale: string) {
  return locale === "ar" ? node.name_ar : locale === "en" ? node.name_en : node.name_he;
}

function flatten(nodes: CategoryNode[], acc: CategoryNode[] = []): CategoryNode[] {
  for (const n of nodes) {
    acc.push(n);
    flatten(n.children, acc);
  }
  return acc;
}

/** Tree of checkboxes. `mode="coverage"` explains for suppliers that a parent covers its children. */
export function CategoryPicker({ value, onChange, max }: { value: string[]; onChange: (ids: string[]) => void; max?: number }) {
  const { locale, t } = useI18n();
  const { tree } = useCategories();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const all = useMemo(() => (tree ? flatten(tree) : []), [tree]);

  if (!tree) return <Spinner />;

  const selected = new Set(value);
  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else if (!max || next.size < max) next.add(id);
    onChange([...next]);
  };

  const q = query.trim().toLowerCase();
  const matches = (n: CategoryNode): boolean =>
    !q || [n.name_he, n.name_ar, n.name_en].some((s) => s.toLowerCase().includes(q)) || n.children.some(matches);

  const render = (nodes: CategoryNode[]) => (
    <ul className="space-y-0.5">
      {nodes.filter(matches).map((n) => {
        const expanded = !!q || open[n.id] || n.children.some((c) => selected.has(c.id) || c.children.some((g) => selected.has(g.id)));
        return (
          <li key={n.id}>
            <div className="flex items-center gap-1">
              {n.children.length > 0 ? (
                <button type="button" onClick={() => setOpen((o) => ({ ...o, [n.id]: !expanded }))} className="rounded p-1 text-muted hover:bg-surface-2" aria-expanded={expanded} aria-label={categoryName(n, locale)}>
                  <ChevronDown className={cx("size-4 transition-transform", !expanded && "ltr:-rotate-90 rtl:rotate-90")} />
                </button>
              ) : <span className="w-6" />}
              <label className={cx("flex flex-1 cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-surface-2", selected.has(n.id) && "bg-primary-soft")}>
                <input type="checkbox" className="size-4 accent-[var(--primary)]" checked={selected.has(n.id)} onChange={() => toggle(n.id)} />
                <span className={cx(n.depth === 0 && "font-medium")}>{categoryName(n, locale)}</span>
              </label>
            </div>
            {n.children.length > 0 && expanded && <div className="ms-6 border-s border-line ps-2">{render(n.children)}</div>}
          </li>
        );
      })}
    </ul>
  );

  return (
    <div className="rounded-lg border border-line-strong bg-surface">
      <div className="relative border-b border-line p-2">
        <Search className="pointer-events-none absolute start-4 top-1/2 size-4 -translate-y-1/2 text-muted" />
        <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("categories.search")} className="ps-9" aria-label={t("categories.search")} />
      </div>
      <div className="max-h-80 overflow-y-auto p-2">{render(tree)}</div>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-t border-line p-2">
          {value.map((id) => {
            const node = all.find((n) => n.id === id);
            return node ? (
              <button type="button" key={id} onClick={() => toggle(id)} className="rounded-full bg-primary-soft px-2.5 py-0.5 text-xs text-primary hover:bg-primary hover:text-white">
                {categoryName(node, locale)} ✕
              </button>
            ) : null;
          })}
        </div>
      )}
    </div>
  );
}
