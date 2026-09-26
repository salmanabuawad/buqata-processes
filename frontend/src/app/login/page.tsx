"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AuthFrame } from "@/components/AuthFrame";
import { Badge, Button, Card, ErrorAlert, Field, Input } from "@/components/ui";
import { useI18n } from "@/i18n/I18nProvider";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";

interface DemoUser { id: string; full_name: string; kind: string; roles: string[]; company: string | null }

function destination(kind: string) {
  const next = new URLSearchParams(window.location.search).get("next");
  if (next && next.startsWith("/") && !next.startsWith("//")) return next;
  return kind === "supplier" ? "/supplier/" : "/dashboard/";
}

export default function LoginPage() {
  const { t } = useI18n();
  const { refresh } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [demoUsers, setDemoUsers] = useState<DemoUser[] | null>(null);

  useEffect(() => {
    api.get<{ demo_mode: boolean }>("/meta").then((m) => {
      if (m.demo_mode) api.get<DemoUser[]>("/auth/demo-users").then(setDemoUsers).catch(() => undefined);
    }).catch(() => undefined);
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/login", { email, password });
      const me = await refresh();
      window.location.href = destination(me?.kind ?? "staff");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const demoLogin = async (user: DemoUser) => {
    setError(null);
    try {
      await api.post("/auth/demo-login", { user_id: user.id });
      await refresh();
      window.location.href = destination(user.kind);
    } catch (err) {
      setError(err);
    }
  };

  return (
    <AuthFrame wide={!!demoUsers}>
      <div className={demoUsers ? "grid gap-6 md:grid-cols-2" : ""}>
        <Card className="p-6">
          <h1 className="text-xl font-semibold">{t("auth.sign_in")}</h1>
          <p className="mt-1 text-sm text-muted">{t("auth.sign_in_hint")}</p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <Field label={t("auth.email")} required>
              {(id) => <Input id={id} type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} dir="ltr" />}
            </Field>
            <Field label={t("auth.password")} required>
              {(id) => <Input id={id} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} dir="ltr" />}
            </Field>
            <ErrorAlert error={error} />
            <Button type="submit" busy={busy} className="w-full">{t("auth.sign_in")}</Button>
          </form>
          <p className="mt-4 text-sm text-muted">{t("auth.staff_sso_note")}</p>
          <p className="mt-6 border-t border-line pt-4 text-sm">
            {t("auth.no_account")} <Link href="/register/" className="font-medium text-primary underline">{t("auth.register_supplier")}</Link>
          </p>
        </Card>
        {demoUsers && (
          <Card className="p-6">
            <div className="flex items-center gap-2">
              <h2 className="font-semibold">{t("auth.demo_title")}</h2>
              <Badge tone="warn">{t("auth.demo_badge")}</Badge>
            </div>
            <p className="mt-1 text-sm text-muted">{t("auth.demo_hint")}</p>
            <ul className="mt-4 divide-y divide-line">
              {demoUsers.map((u) => (
                <li key={u.id}>
                  <button onClick={() => demoLogin(u)} className="flex w-full items-center justify-between gap-3 rounded-lg px-2 py-2.5 text-start hover:bg-surface-2">
                    <span>
                      <span className="block text-sm font-medium">{u.full_name}</span>
                      <span className="block text-xs text-muted">{u.company ?? u.roles.map((r) => t(`roles.${r}`)).join(" · ")}</span>
                    </span>
                    <Badge tone={u.kind === "supplier" ? "success" : "primary"}>{t(`kinds.${u.kind}`)}</Badge>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </AuthFrame>
  );
}
