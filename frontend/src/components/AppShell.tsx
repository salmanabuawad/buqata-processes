"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  Bell,
  Building2,
  ClipboardList,
  FolderTree,
  LayoutDashboard,
  LogOut,
  Menu,
  PlusCircle,
  ScrollText,
  ShieldCheck,
  Store,
  UserCog,
  UserRound,
  X,
} from "lucide-react";
import { LOCALES, useI18n } from "@/i18n/I18nProvider";
import { useSession } from "@/lib/session";
import { api, formatDateTime } from "@/lib/api";
import { cx, Spinner } from "./ui";

export function Emblem({ className }: { className?: string }) {
  // Stylised hills and a roof line — a neutral mark, not the council's official emblem.
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden>
      <rect width="48" height="48" rx="11" fill="#1b4f8f" />
      <path d="M8 34c6-7 11-9 16-6s10 2 16-5v17H8z" fill="#2b7449" />
      <path d="M8 38c7-5 13-6 20-3s9 1 12-1v6H8z" fill="#4c9a69" />
      <path d="M14 21l10-8 10 8" stroke="#fff" strokeWidth="2.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="24" cy="23" r="2.4" fill="#fff" />
    </svg>
  );
}

function LanguageSwitcher({ compact }: { compact?: boolean }) {
  const { locale, setLocale, t } = useI18n();
  return (
    <div role="group" aria-label={t("common.language")} className="flex overflow-hidden rounded-lg border border-line bg-surface text-sm">
      {LOCALES.map((l) => (
        <button
          key={l.code}
          onClick={() => setLocale(l.code)}
          aria-pressed={locale === l.code}
          lang={l.code}
          className={cx("px-2.5 py-1.5 transition-colors", locale === l.code ? "bg-primary text-white" : "text-ink-2 hover:bg-surface-2")}
        >
          {compact ? l.code.toUpperCase() : l.label}
        </button>
      ))}
    </div>
  );
}

interface NotificationItem {
  id: string; subject: string; body: string; link: string | null; created_at: string; read: boolean;
}

function NotificationBell() {
  const { t, locale } = useI18n();
  const { me, refresh } = useSession();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[] | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    api.get<{ items: NotificationItem[] }>("/notifications").then((r) => setItems(r.items)).catch(() => setItems([]));
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const markAll = async () => {
    await api.post("/notifications/read-all");
    setItems((current) => current?.map((n) => ({ ...n, read: true })) ?? null);
    void refresh();
  };

  const unread = me?.unread_notifications ?? 0;
  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative rounded-lg p-2 text-ink-2 hover:bg-surface-2"
        aria-label={t("nav.notifications")}
        aria-expanded={open}
      >
        <Bell className="size-5" />
        {unread > 0 && (
          <span className="absolute -top-0.5 end-0 min-w-5 rounded-full bg-danger px-1 text-center text-[11px] font-semibold leading-5 text-white">{unread}</span>
        )}
      </button>
      {open && (
        <div className="absolute end-0 z-40 mt-2 w-[min(380px,calc(100vw-24px))] rounded-xl border border-line bg-surface shadow-xl">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <span className="font-semibold">{t("nav.notifications")}</span>
            {unread > 0 && <button onClick={markAll} className="text-sm text-primary hover:underline">{t("notifications.mark_all")}</button>}
          </div>
          <div className="max-h-96 overflow-y-auto">
            {items === null ? <Spinner /> : items.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-muted">{t("notifications.empty")}</p>
            ) : items.map((n) => (
              <a key={n.id} href={n.link && n.link.startsWith("/") ? n.link : "#"} className={cx("block border-b border-line px-4 py-3 last:border-0 hover:bg-surface-2", !n.read && "bg-primary-soft/50")}>
                <div className="text-sm font-medium text-ink">{n.subject}</div>
                <div className="mt-0.5 line-clamp-2 whitespace-pre-line text-xs text-muted">{n.body}</div>
                <div className="mt-1 text-[11px] text-muted ltr" style={{ textAlign: "start" }}>{formatDateTime(n.created_at, locale)}</div>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

interface NavItem { href: string; label: string; icon: React.ReactNode; show: boolean }

function useNav(): NavItem[] {
  const { t } = useI18n();
  const { me, can } = useSession();
  if (!me) return [];
  if (me.kind === "supplier") {
    return [
      { href: "/supplier/", label: t("nav.opportunities"), icon: <ClipboardList className="size-4" />, show: true },
      { href: "/supplier/profile/", label: t("nav.company_profile"), icon: <Store className="size-4" />, show: true },
    ];
  }
  return [
    { href: "/dashboard/", label: t("nav.dashboard"), icon: <LayoutDashboard className="size-4" />, show: can("process.read") },
    { href: "/processes/", label: t("nav.processes"), icon: <ClipboardList className="size-4" />, show: can("process.read") },
    { href: "/processes/new/", label: t("nav.new_process"), icon: <PlusCircle className="size-4" />, show: can("process.create.rfq") },
    { href: "/suppliers/", label: t("nav.suppliers"), icon: <Building2 className="size-4" />, show: can("supplier.registry.read") },
    { href: "/audit/", label: t("nav.audit"), icon: <ScrollText className="size-4" />, show: can("audit.read") || can("audit.verify") },
    { href: "/admin/categories/", label: t("nav.categories"), icon: <FolderTree className="size-4" />, show: can("category.manage") },
    { href: "/admin/users/", label: t("nav.users"), icon: <UserCog className="size-4" />, show: can("user.manage") },
  ].filter((i) => i.show);
}

export function Principles({ className }: { className?: string }) {
  const { t } = useI18n();
  return (
    <div className={cx("flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-xs text-muted", className)}>
      {["efficiency", "transparency", "equal_opportunity", "security"].map((k, i) => (
        <span key={k} className="flex items-center gap-3">
          {i > 0 && <span aria-hidden className="text-line-strong">|</span>}
          {t(`principles.${k}`)}
        </span>
      ))}
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const { me, loading, logout } = useSession();
  const nav = useNav();
  const pathname = usePathname();
  const router = useRouter();
  // The mobile menu belongs to the page it was opened on; navigating closes it.
  const [mobileOpenOn, setMobileOpenOn] = useState<string | null>(null);
  const mobileOpen = mobileOpenOn !== null && mobileOpenOn === pathname;
  const setMobileOpen = (value: boolean) => setMobileOpenOn(value ? pathname : null);

  useEffect(() => {
    if (!loading && !me) router.replace(`/login/?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
  }, [loading, me, router]);

  if (loading || !me) return <Spinner />;

  const home = me.kind === "supplier" ? "/supplier/" : "/dashboard/";
  const navList = (
    <nav aria-label={t("nav.main")} className="space-y-1">
      {nav.map((item) => {
        const active = pathname === item.href || (item.href !== "/processes/" && pathname?.startsWith(item.href)) ||
          (item.href === "/processes/" && pathname?.startsWith("/process"));
        const exactNew = item.href === "/processes/new/" && pathname?.startsWith("/processes/new");
        const isActive = item.href === "/processes/" ? active && !pathname?.startsWith("/processes/new") : active || exactNew;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive ? "page" : undefined}
            className={cx(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              isActive ? "bg-primary-soft text-primary" : "text-ink-2 hover:bg-surface-2 hover:text-ink",
            )}
          >
            {item.icon}
            {item.label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen">
      <a href="#main" className="skip-link">{t("common.skip_to_content")}</a>
      <header className="no-print sticky top-0 z-30 border-b border-line bg-surface/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1400px] items-center gap-3 px-4">
          <button className="rounded-lg p-2 hover:bg-surface-2 lg:hidden" onClick={() => setMobileOpen(true)} aria-label={t("nav.open_menu")}>
            <Menu className="size-5" />
          </button>
          <Link href={home} className="flex min-w-0 items-center gap-3">
            <Emblem className="size-9 shrink-0" />
            <div className="min-w-0 leading-tight">
              <div className="truncate text-[15px] font-semibold text-ink">{t("app.name")}</div>
              <div className="truncate text-xs text-muted">{t("app.council")}</div>
            </div>
          </Link>
          <div className="ms-auto flex items-center gap-2">
            <div className="hidden sm:block"><LanguageSwitcher /></div>
            <div className="sm:hidden"><LanguageSwitcher compact /></div>
            <NotificationBell />
            <div className="hidden items-center gap-2 border-s border-line ps-3 md:flex">
              <UserRound className="size-4 text-muted" />
              <div className="leading-tight">
                <div className="text-sm font-medium">{me.full_name}</div>
                <div className="text-xs text-muted">{me.supplier?.company_name ?? me.roles.map((r) => t(`roles.${r}`)).join(" · ")}</div>
              </div>
            </div>
            <button onClick={logout} className="rounded-lg p-2 text-ink-2 hover:bg-surface-2" aria-label={t("nav.logout")} title={t("nav.logout")}>
              <LogOut className="size-5 rtl:-scale-x-100" />
            </button>
          </div>
        </div>
      </header>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setMobileOpen(false)} />
          <div className="absolute inset-y-0 start-0 w-72 bg-surface p-4 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <span className="font-semibold">{t("nav.main")}</span>
              <button onClick={() => setMobileOpen(false)} className="rounded-lg p-2 hover:bg-surface-2" aria-label={t("common.close")}><X className="size-5" /></button>
            </div>
            {navList}
          </div>
        </div>
      )}

      <div className="mx-auto flex max-w-[1400px] gap-6 px-4 py-6">
        <aside className="no-print hidden w-60 shrink-0 lg:block">
          <div className="sticky top-22">
            {navList}
            <div className="mt-6 rounded-xl border border-line bg-surface p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-ink"><ShieldCheck className="size-4 text-accent" />{t("shell.trust_title")}</div>
              <p className="mt-1 text-xs leading-relaxed text-muted">{t("shell.trust_body")}</p>
            </div>
          </div>
        </aside>
        <main id="main" className="min-w-0 flex-1">{children}</main>
      </div>
      <footer className="no-print border-t border-line py-4">
        <Principles />
      </footer>
    </div>
  );
}

export { LanguageSwitcher };
