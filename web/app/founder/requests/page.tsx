"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge, EmptyState, ErrorState, LockedCard } from "@/components/ui/states";
import { ConfirmDialog } from "@/components/ui/dialog";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { PanelList, PanelRow, SectionLabel } from "@/components/ui/panel";
import { api, type CallRequest } from "@/lib/api";
import { gate, gateCopy } from "@/lib/domain/access";
import { founderAccount, humanize } from "@/lib/format";
import { formatSlot } from "@/lib/utils";
import { useSession } from "@/stores/session";
import { toast } from "sonner";
import { useLoad } from "@/lib/hooks/use-load";
import { useStartup } from "@/lib/hooks/use-startup";

export default function RequestsPage() {
  const session = useSession((s) => s.session);
  const { profile, loading: profileLoading, error: profileError, reload: reloadProfile } = useStartup();
  const g = gate(founderAccount(session), "investorRequests");
  const load = useLoad(() => api.listCalls(), [], (d) => d.length === 0);
  const [declineId, setDeclineId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  if (!g.allowed) {
    const copy = gateCopy(g.reason, "founder");
    return (
      <LockedCard
        title={copy.title}
        body={copy.body}
        cta={copy.cta}
        href={g.reason === "payment" ? "/founder/paywall" : "/verify-email"}
      />
    );
  }

  if (profileLoading) return <PageSkeleton />;
  if (profileError) return <ErrorState message={profileError} onRetry={() => void reloadProfile()} />;
  if (!profile) {
    return (
      <EmptyState
        title="No company on file"
        body="Complete intake so investor calls have a company to land on."
        action={<Button href="/onboarding">Start intake</Button>}
      />
    );
  }

  if (load.status === "loading") return <PageSkeleton />;
  if (load.status === "error") return <ErrorState message={load.message} onRetry={() => void load.reload()} />;
  if (load.status === "empty") {
    return (
      <div className="space-y-6">
        <PageHeader title="Investor requests" />
        <EmptyState title="No requests" body="When an investor proposes a call, it lands here." />
      </div>
    );
  }

  const calls = load.data;
  const pending = calls.filter((c) => c.status === "pending");
  const rest = calls.filter((c) => c.status !== "pending");

  async function respond(c: CallRequest, accept: boolean) {
    setBusyId(c.id);
    try {
      await api.respondCall(c.id, accept);
      toast.success(accept ? "Accepted." : "Declined.");
      await load.reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not respond.");
    } finally {
      setBusyId(null);
      setDeclineId(null);
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader title="Investor requests" description="Accept or decline proposed slots. The investor never sees your notes to SACI." />
      <section className="space-y-3">
        <SectionLabel>Pending</SectionLabel>
        {pending.length === 0 ? (
          <p className="text-sm text-mist">Nothing waiting. Earlier replies are listed below.</p>
        ) : (
          <PanelList>
            {pending.map((c) => (
              <PanelRow key={c.id} className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="text-sm text-cream">Investor · {formatSlot(c.proposed_at)}</p>
                  {c.message ? <p className="mt-1 text-xs text-mist">{c.message}</p> : null}
                </div>
                <div className="flex gap-2">
                  <Button type="button" loading={busyId === c.id} onClick={() => void respond(c, true)}>
                    Accept
                  </Button>
                  <Button type="button" variant="ghost" onClick={() => setDeclineId(c.id)}>
                    Decline
                  </Button>
                </div>
              </PanelRow>
            ))}
          </PanelList>
        )}
      </section>
      {rest.length ? (
        <section className="space-y-3">
          <SectionLabel>Answered</SectionLabel>
          <PanelList>
            {rest.map((c) => (
              <PanelRow key={c.id} className="flex items-center justify-between text-sm">
                <span>Investor · {formatSlot(c.proposed_at)}</span>
                <Badge tone={c.status === "accepted" ? "pass" : "fail"}>{humanize(c.status)}</Badge>
              </PanelRow>
            ))}
          </PanelList>
        </section>
      ) : null}
      <ConfirmDialog
        open={Boolean(declineId)}
        title="Decline this call?"
        body="The investor is notified. You can still take other requests."
        confirmLabel="Decline"
        danger
        onClose={() => setDeclineId(null)}
        onConfirm={() => {
          const row = pending.find((c) => c.id === declineId);
          if (row) void respond(row, false);
        }}
      />
    </div>
  );
}
