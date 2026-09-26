"use client";

import { useEffect, useState } from "react";
import { AuthFrame } from "@/components/AuthFrame";
import { Alert, Card, LinkButton, Spinner } from "@/components/ui";
import { useI18n } from "@/i18n/I18nProvider";
import { api } from "@/lib/api";
import { useQueryParam, useSession } from "@/lib/session";

// Opening an invitation link records that the invitation was opened (for the
// fairness report). It never signs anyone in.
export default function InvitePage() {
  const { t } = useI18n();
  const { me, loading } = useSession();
  const token = useQueryParam("token");
  const [process, setProcess] = useState<{ process_id: string; reference_number: string; title: string } | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!token) return;
    api.get<{ process_id: string; reference_number: string; title: string }>(`/invitations/${encodeURIComponent(token)}`)
      .then(setProcess).catch(() => setFailed(true));
  }, [token]);

  useEffect(() => {
    if (process && !loading && me?.kind === "supplier") window.location.href = `/supplier/opportunity/?id=${process.process_id}`;
  }, [process, loading, me]);

  const target = process ? `/supplier/opportunity/?id=${process.process_id}` : "/supplier/";
  return (
    <AuthFrame>
      <Card className="p-6">
        {failed ? <Alert tone="danger" title={t("invite.invalid")} /> : !process ? <Spinner /> : (
          <>
            <p className="text-sm text-muted">{t("invite.kicker")}</p>
            <h1 className="mt-1 text-xl font-semibold">{process.title}</h1>
            <p className="mt-1 text-sm ltr" style={{ textAlign: "start" }}>{process.reference_number}</p>
            <p className="mt-4 text-sm text-ink-2">{t("invite.body")}</p>
            <LinkButton href={`/login/?next=${encodeURIComponent(target)}`} className="mt-6 w-full">{t("invite.continue")}</LinkButton>
          </>
        )}
      </Card>
    </AuthFrame>
  );
}
