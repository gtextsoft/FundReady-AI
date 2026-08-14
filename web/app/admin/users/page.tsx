"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/field";
import { Badge, EmptyState, ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Panel, PanelList, PanelRow } from "@/components/ui/panel";
import { api, type UserRow } from "@/lib/api";
import { checkPassword, PASSWORD_HINT } from "@/lib/domain/access";
import { humanize } from "@/lib/format";
import { useLoad } from "@/lib/hooks/use-load";
import { toast } from "sonner";

export default function AdminUsersPage() {
  const [role, setRole] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useLoad(
    async () => {
      const qs = role ? `?role=${role}` : "";
      const page = await api.listUsers(qs);
      return page.items;
    },
    [role],
    (d) => d.length === 0,
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Users" />
      <Panel className="max-w-xs">
        <Select label="Role" value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">Any</option>
          <option value="founder">Founder</option>
          <option value="investor">Investor</option>
          <option value="admin">Admin</option>
        </Select>
      </Panel>
      <Panel>
        <p className="text-sm text-mist">Provision another admin. They must verify email and enrol MFA.</p>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <Field label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <Field label="Password" type="password" hint={PASSWORD_HINT} value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {formError ? <p className="mt-2 text-sm text-fail">{formError}</p> : null}
        <Button
          className="mt-3"
          type="button"
          loading={busy}
          onClick={async () => {
            if (!email.includes("@")) {
              setFormError("Enter a valid email.");
              return;
            }
            const pw = checkPassword(password);
            if (!pw.ok) {
              setFormError(pw.message);
              return;
            }
            setFormError(null);
            setBusy(true);
            try {
              await api.provisionAdmin(email.trim(), password);
              toast.success("Admin provisioned.");
              setEmail("");
              setPassword("");
              await load.reload();
            } catch (err) {
              toast.error(err instanceof Error ? err.message : "Could not provision.");
            } finally {
              setBusy(false);
            }
          }}
        >
          Provision
        </Button>
      </Panel>
      {load.status === "loading" ? <PageSkeleton /> : null}
      {load.status === "error" ? <ErrorState message={load.message} onRetry={() => void load.reload()} /> : null}
      {load.status === "empty" ? <EmptyState title="No users" body="Nothing matches this filter." /> : null}
      {load.status === "ready" ? (
        <PanelList>
          {load.data.map((u: UserRow) => (
            <PanelRow key={u.id} className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm text-cream">{u.email}</p>
                <p className="text-[11px] text-mist">
                  {humanize(u.role)} · {humanize(u.status)}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Badge tone={u.mfa_enabled ? "pass" : "hold"}>{u.mfa_enabled ? "MFA" : "no MFA"}</Badge>
                {u.status !== "suspended" ? (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={async () => {
                      await api.suspendUser(u.id);
                      await load.reload();
                    }}
                  >
                    Suspend
                  </Button>
                ) : (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={async () => {
                      await api.reactivateUser(u.id);
                      await load.reload();
                    }}
                  >
                    Reactivate
                  </Button>
                )}
              </div>
            </PanelRow>
          ))}
        </PanelList>
      ) : null}
    </div>
  );
}
