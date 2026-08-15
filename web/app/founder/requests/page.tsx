"use client";

import { Badge, EmptyState, ErrorState, LockedCard } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { PanelList, PanelRow } from "@/components/ui/panel";
import { api, type Meeting } from "@/lib/api";
import { gate, gateCopy } from "@/lib/domain/access";
import { founderAccount, humanize } from "@/lib/format";
import { formatSlot } from "@/lib/utils";
import { useSession } from "@/stores/session";
import { useLoad } from "@/lib/hooks/use-load";
import { useStartup } from "@/lib/hooks/use-startup";
import { Button } from "@/components/ui/button";

export default function RequestsPage() {
  const session = useSession((s) => s.session);
  const { profile, loading: profileLoading, error: profileError, reload: reloadProfile } = useStartup();
  const g = gate(founderAccount(session), "investorRequests");
  const load = useLoad(() => api.listMyMeetings(), [], (d) => d.length === 0);

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
        body="Complete intake so SACI has a company to introduce."
        action={<Button href="/onboarding">Start intake</Button>}
      />
    );
  }

  if (load.status === "loading") return <PageSkeleton />;
  if (load.status === "error") return <ErrorState message={load.message} onRetry={() => void load.reload()} />;
  if (load.status === "empty") {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Meetings"
          description="SACI books introductions. Time and location appear here after confirmation."
        />
        <EmptyState
          title="No meetings yet"
          body="SACI hosts every introduction. When a meeting is confirmed, the slot lands here."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Meetings"
        description="SACI hosts every introduction. You see a meeting only after it is confirmed."
      />
      <PanelList>
        {load.data.map((m: Meeting) => (
          <PanelRow key={m.id} className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm text-cream">{formatSlot(m.scheduled_at)}</p>
              <p className="mt-1 text-xs text-mist">
                {m.duration_minutes} minutes
                {m.location ? ` · ${m.location}` : ""}
              </p>
              {m.notes ? <p className="mt-1 text-xs text-mist">{m.notes}</p> : null}
            </div>
            <Badge tone="pass">{humanize(m.status)}</Badge>
          </PanelRow>
        ))}
      </PanelList>
    </div>
  );
}
