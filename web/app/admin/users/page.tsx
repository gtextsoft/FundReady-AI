"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/field";
import { Badge, EmptyState, ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Panel, PanelList, PanelRow } from "@/components/ui/panel";
import { api, queryString, type Page, type UserRow } from "@/lib/api";
import { checkPassword, PASSWORD_HINT } from "@/lib/domain/access";
import { humanize } from "@/lib/format";
import { useLoad } from "@/lib/hooks/use-load";
import { toast } from "sonner";

const PAGE_SIZE = 20;

export default function AdminUsersPage() {
  const [role, setRole] = useState("");
  const [accountStatus, setAccountStatus] = useState("");
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState("");
  const [offset, setOffset] = useState(0);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useLoad(
    async () => {
      return api.listUsers(
        queryString({
          q: applied || undefined,
          role: role || undefined,
          status: accountStatus || undefined,
          limit: PAGE_SIZE,
          offset,
        }),
      );
    },
    [applied, role, accountStatus, offset],
    (d) => d.total === 0,
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Users" />
      <Panel className="grid gap-3 md:grid-cols-3">
        <Field
          label="Search"
          placeholder="Email or name"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              setOffset(0);
              setApplied(q.trim());
            }
          }}
        />
        <Select
          label="Role"
          value={role}
          onChange={(e) => {
            setOffset(0);
            setRole(e.target.value);
          }}
        >
          <option value="">Any</option>
          <option value="founder">Founder</option>
          <option value="investor">Investor</option>
          <option value="admin">Admin</option>
        </Select>
        <Select
          label="Status"
          value={accountStatus}
          onChange={(e) => {
            setOffset(0);
            setAccountStatus(e.target.value);
          }}
        >
          <option value="">Any</option>
          <option value="pending_verification">Pending verification</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
        </Select>
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            setOffset(0);
            setApplied(q.trim());
          }}
        >
          Apply search
        </Button>
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
        <UserResults page={load.data} offset={offset} onPage={setOffset} onChanged={load.reload} />
      ) : null}
    </div>
  );
}

function UserResults({
  page,
  offset,
  onPage,
  onChanged,
}: {
  page: Page<UserRow>;
  offset: number;
  onPage: (next: number) => void;
  onChanged: () => Promise<void>;
}) {
  const from = page.total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + page.items.length, page.total);
  return (
    <>
      <p className="text-sm text-mist tabular-nums">
        {from}–{to} of {page.total}
      </p>
      <PanelList>
        {page.items.map((u) => (
          <PanelRow key={u.id} className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm text-cream">{u.email}</p>
              <p className="text-[11px] text-mist">
                {[u.first_name, u.last_name].filter(Boolean).join(" ") || "—"} · {humanize(u.role)} · {humanize(u.status)}
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
                    await onChanged();
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
                    await onChanged();
                  }}
                >
                  Reactivate
                </Button>
              )}
            </div>
          </PanelRow>
        ))}
      </PanelList>
      <div className="flex gap-2">
        <Button type="button" variant="ghost" disabled={offset === 0} onClick={() => onPage(Math.max(0, offset - PAGE_SIZE))}>
          Previous
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={offset + PAGE_SIZE >= page.total}
          onClick={() => onPage(offset + PAGE_SIZE)}
        >
          Next
        </Button>
      </div>
    </>
  );
}
