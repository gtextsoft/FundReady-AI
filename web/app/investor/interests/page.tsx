"use client";

import { useState } from "react";
import Link from "next/link";
import { Badge, EmptyState, ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { PanelList, PanelRow } from "@/components/ui/panel";
import { api, type Interest, type Meeting } from "@/lib/api";
import { humanize } from "@/lib/format";
import { formatSlot } from "@/lib/utils";
import { useLoad } from "@/lib/hooks/use-load";
import { toast } from "sonner";

export default function InterestsPage() {
  const load = useLoad(
    async () => {
      const items = await api.listInterests();
      const page = await api.discover("").catch(() => ({ items: [] as { startup_id: string; name: string | null }[] }));
      const names: Record<string, string> = {};
      for (const c of page.items) names[c.startup_id] = c.name ?? c.startup_id.slice(0, 8);
      const meetings: Record<string, Meeting[]> = {};
      await Promise.all(
        items
          .filter((i) => i.status === "approved")
          .map(async (i) => {
            meetings[i.id] = await api.listMeetings(i.id).catch(() => []);
          }),
      );
      return { items, names, meetings };
    },
    [],
    (d) => d.items.length === 0,
  );
  const [busyId, setBusyId] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <PageHeader title="My interests" description="SACI decides what happens next. Revealed reports appear here." />
      {load.status === "loading" ? <PageSkeleton /> : null}
      {load.status === "error" ? <ErrorState message={load.message} onRetry={() => void load.reload()} /> : null}
      {load.status === "empty" ? (
        <EmptyState
          title="No interest filed"
          body="Express interest from a company card. SACI decides what happens next."
          action={<Button href="/investor">Browse dealflow</Button>}
        />
      ) : null}
      {load.status === "ready" ? (
        <PanelList>
          {load.data.items.map((i: Interest) => (
            <PanelRow key={i.id} className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-lg font-semibold tracking-[-0.02em] text-cream">
                    {load.data.names[i.startup_id] ?? "Company"}
                  </p>
                  {i.revealed_run_ids[0] ? (
                    <Link href={`/investor/report/${i.id}/${i.revealed_run_ids[0]}`} className="text-sm font-semibold text-brand">
                      Open revealed report →
                    </Link>
                  ) : (
                    <p className="text-sm text-mist">No report revealed yet</p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={i.status === "approved" ? "pass" : i.status === "declined" ? "fail" : "hold"}>
                    {humanize(i.status)}
                  </Badge>
                  {i.status === "pending" ? (
                    <Button
                      type="button"
                      variant="ghost"
                      loading={busyId === i.id}
                      onClick={async () => {
                        setBusyId(i.id);
                        try {
                          await api.withdrawInterest(i.id);
                          toast.success("Interest withdrawn.");
                          await load.reload();
                        } catch (err) {
                          toast.error(err instanceof Error ? err.message : "Could not withdraw.");
                        } finally {
                          setBusyId(null);
                        }
                      }}
                    >
                      Withdraw
                    </Button>
                  ) : null}
                </div>
              </div>
              {(load.data.meetings[i.id] ?? []).length ? (
                <ul className="text-sm text-mist">
                  {load.data.meetings[i.id].map((m) => (
                    <li key={m.id}>
                      {formatSlot(m.scheduled_at)} · {humanize(m.status)}
                      {m.location ? ` · ${m.location}` : ""}
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelRow>
          ))}
        </PanelList>
      ) : null}
    </div>
  );
}
