"use client";

import Link from "next/link";
import { Badge, EmptyState, ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { PanelList, PanelRow } from "@/components/ui/panel";
import { api, type Interest } from "@/lib/api";
import { humanize } from "@/lib/format";
import { useLoad } from "@/lib/hooks/use-load";

export default function InterestsPage() {
  const load = useLoad(
    async () => {
      const items = await api.listInterests();
      const page = await api.discover("");
      const names: Record<string, string> = {};
      for (const c of page.items) names[c.startup_id] = c.name ?? c.startup_id.slice(0, 8);
      return { items, names };
    },
    [],
    (d) => d.items.length === 0,
  );

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
            <PanelRow key={i.id} className="flex items-center justify-between">
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
              <Badge tone={i.status === "approved" ? "pass" : i.status === "declined" ? "fail" : "hold"}>
                {humanize(i.status)}
              </Badge>
            </PanelRow>
          ))}
        </PanelList>
      ) : null}
    </div>
  );
}
