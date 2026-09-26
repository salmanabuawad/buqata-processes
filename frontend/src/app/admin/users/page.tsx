"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Alert, Badge, Button, Card, ErrorAlert, Field, Input, Modal, PageHeader, Select, Spinner, Table } from "@/components/ui";
import { useI18n } from "@/i18n/I18nProvider";
import { api, formatDateTime } from "@/lib/api";
import { useSession } from "@/lib/session";

interface UserRow { id: string; email: string; full_name: string; kind: string; is_active: boolean; roles: string[]; last_login_at: string | null }
interface RoleDef { key: string; business: boolean }

export default function UsersAdmin() {
  const { t, locale } = useI18n();
  const { me } = useSession();
  const [users, setUsers] = useState<UserRow[] | null>(null);
  const [roles, setRoles] = useState<RoleDef[]>([]);
  const [kind, setKind] = useState("staff");
  const [grant, setGrant] = useState<{ user: UserRow; role: string; reason: string } | null>(null);
  const [create, setCreate] = useState<{ email: string; full_name: string; password: string } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api.get<UserRow[]>(`/admin/users?kind=${kind}`).then(setUsers).catch(setError), [kind]);
  useEffect(() => { void load(); api.get<RoleDef[]>("/admin/roles").then(setRoles).catch(() => undefined); }, [load]);

  const doGrant = async () => {
    if (!grant) return;
    setBusy(true); setError(null);
    try { await api.post(`/admin/users/${grant.user.id}/roles`, { role_key: grant.role, reason: grant.reason }); setGrant(null); await load(); }
    catch (err) { setError(err); } finally { setBusy(false); }
  };
  const revoke = async (user: UserRow, role: string) => {
    setError(null);
    try { await api.del(`/admin/users/${user.id}/roles/${role}`); await load(); } catch (err) { setError(err); }
  };
  const toggleActive = async (user: UserRow) => {
    setError(null);
    try { await api.patch(`/admin/users/${user.id}`, { is_active: !user.is_active }); await load(); } catch (err) { setError(err); }
  };
  const doCreate = async () => {
    if (!create) return;
    setBusy(true); setError(null);
    try { await api.post("/admin/users", { ...create, password: create.password || null }); setCreate(null); await load(); }
    catch (err) { setError(err); } finally { setBusy(false); }
  };

  return (
    <AppShell>
      <PageHeader title={t("users.title")} subtitle={t("users.subtitle")}
        actions={<Button onClick={() => setCreate({ email: "", full_name: "", password: "" })}><Plus className="size-4" />{t("users.add")}</Button>} />
      <div className="mb-4"><Alert tone="primary" title={t("users.sod_title")}>{t("users.sod_body")}</Alert></div>
      <ErrorAlert error={error} />
      <Card className="mt-4">
        <div className="border-b border-line p-4">
          <Select value={kind} onChange={(e) => setKind(e.target.value)} className="w-48" aria-label={t("users.kind")}>
            <option value="staff">{t("kinds.staff")}</option>
            <option value="supplier">{t("kinds.supplier")}</option>
          </Select>
        </div>
        {!users ? <Spinner /> : (
          <Table>
            <thead><tr><th>{t("users.name")}</th><th>{t("auth.email")}</th><th>{t("users.roles")}</th><th>{t("users.last_login")}</th><th /></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className={u.is_active ? "" : "opacity-60"}>
                  <td className="font-medium">{u.full_name}{u.id === me?.id && <span className="ms-2 text-xs text-muted">({t("users.you")})</span>}</td>
                  <td className="ltr" style={{ textAlign: "start" }}>{u.email}</td>
                  <td>
                    <div className="flex flex-wrap gap-1">
                      {u.roles.map((r) => (
                        <Badge key={r} tone="primary">
                          {t(`roles.${r}`)}
                          {u.id !== me?.id && u.kind === "staff" && <button onClick={() => revoke(u, r)} className="ms-1 hover:text-danger" aria-label={t("users.revoke")}>✕</button>}
                        </Badge>
                      ))}
                    </div>
                  </td>
                  <td className="ltr whitespace-nowrap text-xs">{formatDateTime(u.last_login_at, locale)}</td>
                  <td className="whitespace-nowrap">
                    {u.kind === "staff" && u.id !== me?.id && (
                      <>
                        <Button size="sm" variant="ghost" onClick={() => setGrant({ user: u, role: roles.find((r) => r.business)?.key ?? "", reason: "" })}>{t("users.grant")}</Button>
                        <Button size="sm" variant="ghost" onClick={() => toggleActive(u)}>{u.is_active ? t("users.deactivate") : t("users.activate")}</Button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      <Modal open={!!grant} onClose={() => setGrant(null)} title={t("users.grant_title", { name: grant?.user.full_name ?? "" })}
        footer={<><Button variant="ghost" onClick={() => setGrant(null)}>{t("common.cancel")}</Button><Button onClick={doGrant} busy={busy} disabled={!grant || grant.reason.trim().length < 5}>{t("users.grant")}</Button></>}>
        {grant && (
          <div className="space-y-4">
            <Field label={t("users.role")}>{(id) => (
              <Select id={id} value={grant.role} onChange={(e) => setGrant({ ...grant, role: e.target.value })}>
                {roles.filter((r) => !["supplier", "applicant"].includes(r.key)).map((r) => <option key={r.key} value={r.key}>{t(`roles.${r.key}`)}</option>)}
              </Select>
            )}</Field>
            <Field label={t("users.reason")} hint={t("users.reason_hint")} required>{(id) => <Input id={id} value={grant.reason} onChange={(e) => setGrant({ ...grant, reason: e.target.value })} />}</Field>
            {roles.find((r) => r.key === grant.role)?.business && <Alert tone="warn">{t("users.business_alert")}</Alert>}
          </div>
        )}
      </Modal>
      <Modal open={!!create} onClose={() => setCreate(null)} title={t("users.add")}
        footer={<><Button variant="ghost" onClick={() => setCreate(null)}>{t("common.cancel")}</Button><Button onClick={doCreate} busy={busy}>{t("common.save")}</Button></>}>
        {create && (
          <div className="space-y-4">
            <Field label={t("users.name")} required>{(id) => <Input id={id} value={create.full_name} onChange={(e) => setCreate({ ...create, full_name: e.target.value })} />}</Field>
            <Field label={t("auth.email")} required>{(id) => <Input id={id} type="email" dir="ltr" value={create.email} onChange={(e) => setCreate({ ...create, email: e.target.value })} />}</Field>
            <Field label={t("auth.password")} hint={t("users.password_hint")}>{(id) => <Input id={id} type="password" dir="ltr" value={create.password} onChange={(e) => setCreate({ ...create, password: e.target.value })} />}</Field>
          </div>
        )}
      </Modal>
    </AppShell>
  );
}
