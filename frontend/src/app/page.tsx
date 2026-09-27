"use client";

import Link from "next/link";
import { ArrowLeft, ArrowRight, Eye, Lock, Scale, Zap } from "lucide-react";
import { Emblem, LanguageSwitcher, Principles } from "@/components/AppShell";
import { Card, LinkButton } from "@/components/ui";
import { useI18n } from "@/i18n/I18nProvider";
import { useSession } from "@/lib/session";

export default function Landing() {
  const { t, dir } = useI18n();
  const { me } = useSession();
  const Arrow = dir === "rtl" ? ArrowLeft : ArrowRight;
  const home = me ? (me.kind === "supplier" ? "/supplier/" : "/dashboard/") : null;

  const principles = [
    // Tile colours follow the app's meaning: blue = process, green = fairness, purple = sealing.
    { key: "efficiency", icon: <Zap className="size-5" />, tile: "bg-primary-soft text-primary" },
    { key: "transparency", icon: <Eye className="size-5" />, tile: "bg-primary-soft text-primary" },
    { key: "equal_opportunity", icon: <Scale className="size-5" />, tile: "bg-accent-soft text-accent" },
    { key: "security", icon: <Lock className="size-5" />, tile: "bg-sealed-soft text-sealed" },
  ];

  return (
    // Full-height column: the footer sits at the bottom on tall screens, and the
    // content is compact enough to fit a typical desktop window without scrolling.
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4">
          <Emblem className="size-9" />
          <div className="leading-tight">
            <div className="font-semibold">{t("app.name")}</div>
            <div className="text-xs text-muted">{t("app.council")}</div>
          </div>
          <div className="ms-auto flex items-center gap-2">
            <LanguageSwitcher />
            {home ? (
              <LinkButton href={home}>{t("landing.to_workspace")}</LinkButton>
            ) : (
              <LinkButton href="/login/" variant="secondary">{t("auth.sign_in")}</LinkButton>
            )}
          </div>
        </div>
      </header>

      <main id="main" className="flex-1">
        <section className="bg-gradient-to-b from-primary-soft to-bg">
          <div className="mx-auto grid max-w-6xl items-center gap-8 px-4 py-8 lg:grid-cols-[1.2fr_1fr] lg:py-6">
            <div>
              <p className="mb-3 inline-flex rounded-full bg-surface px-3 py-1 text-sm text-primary shadow-sm">{t("landing.kicker")}</p>
              <h1 className="text-3xl font-extrabold leading-tight tracking-tight text-ink sm:text-[44px]">{t("landing.title")}</h1>
              <p className="mt-3 max-w-xl text-lg text-ink-2">{t("landing.subtitle")}</p>
              <div className="mt-6 flex flex-wrap gap-3">
                <LinkButton href="/register/" className="h-12 px-6 text-base">{t("landing.cta_supplier")}<Arrow className="size-4" /></LinkButton>
                <LinkButton href="/login/" variant="secondary" className="h-12 px-6 text-base">{t("landing.cta_staff")}</LinkButton>
              </div>
            </div>
            <Card className="p-5">
              <h2 className="font-semibold">{t("landing.how_title")}</h2>
              <ol className="mt-3 space-y-3">
                {[1, 2, 3, 4].map((n) => (
                  <li key={n} className="flex gap-3">
                    <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-white">{n}</span>
                    <div>
                      <div className="font-medium">{t(`landing.step${n}_title`)}</div>
                      <div className="text-sm leading-snug text-muted">{t(`landing.step${n}_body`)}</div>
                    </div>
                  </li>
                ))}
              </ol>
            </Card>
          </div>
        </section>

        <section className="mx-auto max-w-6xl space-y-3 px-4 py-5 lg:py-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {principles.map((p) => (
              <Card key={p.key} className="p-4">
                <div className="flex items-center gap-3">
                  <div className={`flex size-10 shrink-0 items-center justify-center rounded-xl ${p.tile}`}>{p.icon}</div>
                  <h3 className="font-semibold">{t(`principles.${p.key}`)}</h3>
                </div>
                <p className="mt-2 text-sm text-muted">{t(`landing.principle_${p.key}`)}</p>
              </Card>
            ))}
          </div>
          <Card className="grid gap-4 p-5 md:grid-cols-3 lg:p-4">
            {["rfq", "tender", "scholarship"].map((k) => (
              <div key={k}>
                <h3 className="font-semibold">{t(`landing.type_${k}`)}</h3>
                <p className="mt-1 text-sm text-muted">{t(`landing.type_${k}_body`)}</p>
              </div>
            ))}
          </Card>
          <p className="text-center text-sm text-muted">
            {t("landing.supplier_question")} <Link className="text-primary underline" href="/register/">{t("landing.register_link")}</Link>
          </p>
        </section>
      </main>
      <footer className="border-t border-line py-4"><Principles /></footer>
    </div>
  );
}
