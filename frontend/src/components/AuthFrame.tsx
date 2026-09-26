"use client";

import Link from "next/link";
import { Emblem, LanguageSwitcher, Principles } from "./AppShell";
import { useI18n } from "@/i18n/I18nProvider";

export function AuthFrame({ children, wide }: { children: React.ReactNode; wide?: boolean }) {
  const { t } = useI18n();
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4">
          <Link href="/" className="flex items-center gap-3">
            <Emblem className="size-9" />
            <div className="leading-tight">
              <div className="font-semibold">{t("app.name")}</div>
              <div className="text-xs text-muted">{t("app.council")}</div>
            </div>
          </Link>
          <div className="ms-auto"><LanguageSwitcher /></div>
        </div>
      </header>
      <main id="main" className={`mx-auto w-full flex-1 px-4 py-10 ${wide ? "max-w-4xl" : "max-w-md"}`}>{children}</main>
      <footer className="border-t border-line py-4"><Principles /></footer>
    </div>
  );
}
