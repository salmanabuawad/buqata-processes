"use client";

import Link from "next/link";
import { forwardRef, useEffect, useId, useRef } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { ApiError } from "@/lib/api";

export function cx(...parts: unknown[]) {
  return parts.filter((p): p is string => typeof p === "string" && p.length > 0).join(" ");
}

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "success";
const BUTTON: Record<ButtonVariant, string> = {
  primary: "bg-primary text-primary-ink hover:bg-[#163f73] border-transparent",
  secondary: "bg-surface text-ink border-line-strong hover:bg-surface-2",
  ghost: "bg-transparent text-ink-2 border-transparent hover:bg-surface-2",
  danger: "bg-danger text-white border-transparent hover:bg-[#931d14]",
  success: "bg-accent text-white border-transparent hover:bg-[#225e3a]",
};

export const Button = forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: "sm" | "md" | "lg"; busy?: boolean }
>(function Button({ variant = "primary", size = "md", busy, className, children, disabled, ...rest }, ref) {
  return (
    <button
      ref={ref}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg border font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-55",
        size === "sm" && "h-8 px-3 text-sm",
        size === "md" && "h-10 px-4 text-[15px]",
        size === "lg" && "h-12 px-6 text-base",
        BUTTON[variant],
        className,
      )}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy && <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden />}
      {children}
    </button>
  );
});

export function LinkButton({ href, variant = "primary", className, children }: {
  href: string; variant?: ButtonVariant; className?: string; children: React.ReactNode;
}) {
  return (
    <Link href={href} className={cx("inline-flex h-10 items-center justify-center gap-2 rounded-lg border px-4 font-medium transition-colors", BUTTON[variant], className)}>
      {children}
    </Link>
  );
}

export function Card({ className, children, as: As = "section", ...rest }: React.HTMLAttributes<HTMLElement> & { as?: "section" | "div" | "article" }) {
  return (
    <As className={cx("rounded-xl border border-line bg-surface shadow-[0_1px_2px_rgb(15_29_46/0.05)]", className)} {...rest}>
      {children}
    </As>
  );
}

export function CardHeader({ title, subtitle, actions, icon }: { title: React.ReactNode; subtitle?: React.ReactNode; actions?: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
      <div className="flex items-start gap-3">
        {icon && <div className="mt-0.5 text-primary">{icon}</div>}
        <div>
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

type Tone = "neutral" | "primary" | "success" | "warn" | "danger" | "sealed";
const TONE: Record<Tone, string> = {
  neutral: "bg-surface-2 text-ink-2 border-line",
  primary: "bg-primary-soft text-primary border-[#c9dbf2]",
  success: "bg-accent-soft text-accent border-[#c3e3cf]",
  warn: "bg-warn-soft text-warn border-[#f3d9a8]",
  danger: "bg-danger-soft text-danger border-[#f6c6c1]",
  sealed: "bg-sealed-soft text-sealed border-[#d9cdf2]",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: React.ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium", TONE[tone], className)}>
      {children}
    </span>
  );
}

export function Alert({ tone = "primary", title, children }: { tone?: Tone; title?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cx("rounded-lg border px-4 py-3 text-sm", TONE[tone])}>
      {title && <div className="font-semibold">{title}</div>}
      {children && <div className={cx(title && "mt-1", "text-ink-2")}>{children}</div>}
    </div>
  );
}

export function ErrorAlert({ error }: { error: unknown }) {
  const { t, has } = useI18n();
  if (!error) return null;
  let message = t("errors.generic");
  let extra: string | null = null;
  if (error instanceof ApiError) {
    message = has(`errors.${error.code}`) ? t(`errors.${error.code}`) : error.message;
    const missing = (error.details as { missing?: string[] })?.missing;
    if (missing?.length) extra = missing.map((k) => (has(`docs.${k}`) ? t(`docs.${k}`) : k)).join(", ");
    const problems = (error.details as { problems?: string[] })?.problems;
    if (problems?.length) extra = problems.map((k) => (has(`errors.${k}`) ? t(`errors.${k}`) : k)).join(", ");
    const errors = (error.details as { errors?: { loc: string[]; msg: string }[] })?.errors;
    if (Array.isArray(errors) && errors.length) extra = errors.map((e) => `${e.loc.slice(-1)[0]}: ${e.msg}`).join(" · ");
  }
  return <Alert tone="danger" title={message}>{extra}</Alert>;
}

export function Field({ label, hint, error, children, required }: {
  label: React.ReactNode; hint?: React.ReactNode; error?: string | null; children: (id: string) => React.ReactNode; required?: boolean;
}) {
  const id = useId();
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-ink">
        {label}
        {required && <span className="text-danger" aria-hidden> *</span>}
      </label>
      {children(id)}
      {hint && !error && <p className="text-xs text-muted">{hint}</p>}
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}

const INPUT = "w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-[15px] text-ink placeholder:text-muted/70 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:bg-surface-2";

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return <input ref={ref} className={cx(INPUT, "h-10", className)} {...rest} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={cx(INPUT, "min-h-24", className)} {...rest} />;
});

export const Select = forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, children, ...rest }, ref) {
  return <select ref={ref} className={cx(INPUT, "h-10", className)} {...rest}>{children}</select>;
});

export function Stat({ label, value, hint, tone = "neutral", icon }: { label: string; value: React.ReactNode; hint?: React.ReactNode; tone?: Tone; icon?: React.ReactNode }) {
  const accent: Record<Tone, string> = {
    neutral: "text-ink", primary: "text-primary", success: "text-accent", warn: "text-warn", danger: "text-danger", sealed: "text-sealed",
  };
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="text-sm text-muted">{label}</div>
        {icon && <div className={cx("opacity-80", accent[tone])}>{icon}</div>}
      </div>
      <div className={cx("mt-1 text-2xl font-semibold ltr", accent[tone])} style={{ textAlign: "start" }}>{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </Card>
  );
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line-strong bg-surface px-6 py-10 text-center">
      <div className="font-medium text-ink">{title}</div>
      {children && <div className="mt-1 text-sm text-muted">{children}</div>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  const { t } = useI18n();
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-muted" role="status">
      <span className="size-5 animate-spin rounded-full border-2 border-primary border-t-transparent" aria-hidden />
      <span>{label ?? t("common.loading")}</span>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: React.ReactNode; subtitle?: React.ReactNode; actions?: React.ReactNode; eyebrow?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-sm text-muted">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-ink-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { key: T; label: React.ReactNode; badge?: React.ReactNode }[]; value: T; onChange: (key: T) => void }) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-line">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          role="tab"
          aria-selected={value === tab.key}
          onClick={() => onChange(tab.key)}
          className={cx(
            "-mb-px flex items-center gap-2 whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition-colors",
            value === tab.key ? "border-primary text-primary" : "border-transparent text-muted hover:text-ink",
          )}
        >
          {tab.label}
          {tab.badge}
        </button>
      ))}
    </div>
  );
}

export function Modal({ open, onClose, title, children, footer }: { open: boolean; onClose: () => void; title: React.ReactNode; children: React.ReactNode; footer?: React.ReactNode }) {
  const { t } = useI18n();
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      className="m-auto w-[min(640px,calc(100vw-32px))] rounded-xl border border-line bg-surface p-0 text-ink shadow-2xl"
    >
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <h2 className="text-lg font-semibold">{title}</h2>
        <button onClick={onClose} className="rounded-md p-1 text-muted hover:bg-surface-2" aria-label={t("common.close")}><span aria-hidden>✕</span></button>
      </div>
      <div className="max-h-[65vh] overflow-y-auto px-5 py-4">{children}</div>
      {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
    </dialog>
  );
}

export function Table({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cx("overflow-x-auto", className)}>
      <table className="w-full border-collapse text-sm [&_td]:border-b [&_td]:border-line [&_td]:px-4 [&_td]:py-3 [&_th]:border-b [&_th]:border-line [&_th]:bg-surface-2 [&_th]:px-4 [&_th]:py-2.5 [&_th]:text-start [&_th]:font-medium [&_th]:text-ink-2 [&_tr:last-child_td]:border-b-0">
        {children}
      </table>
    </div>
  );
}

export function KeyValue({ items }: { items: [React.ReactNode, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-[max-content_1fr]">
      {items.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-sm text-muted">{k}</dt>
          <dd className="text-sm text-ink">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
