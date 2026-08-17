"use client";

import Link from "next/link";
import { EmptyState, ErrorState, LockedCard } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { api, type StartupCard } from "@/lib/api";
import { useLoad } from "@/lib/hooks/use-load";

export default function WatchlistPage() {
  const load = useLoad(
    async () => {
      const { startup_ids } = await api.getWatchlist();
      const page = await api.discover("");
      return page.items.filter((c) => startup_ids.includes(c.startup_id));
    },
    [],
    (d) => d.length === 0,
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Watchlist" description="Companies you marked from dealflow." />
      {load.status === "loading" ? <PageSkeleton /> : null}
      {load.status === "error" ? (
        load.message.toLowerCase().includes("verification") ? (
          <LockedCard
            title="Thesis required"
            body="SACI reviews who you are and what you look for before dealflow opens."
            cta="Submit your thesis"
            href="/investor/verify"
          />
        ) : (
          <ErrorState message={load.message} onRetry={() => void load.reload()} />
        )
      ) : null}
      {load.status === "empty" ? (
        <EmptyState
          title="Empty watchlist"
          body="Star companies from dealflow to keep them here."
          action={<Button href="/investor">Open dealflow</Button>}
        />
      ) : null}
      {load.status === "ready" ? (
        <ul className="grid gap-3">
          {load.data.map((c: StartupCard) => (
            <li key={c.startup_id}>
              <Link href={`/investor/company/${c.startup_id}`} className="block">
                <Panel className="flex items-baseline gap-3 py-4 transition-shadow hover:shadow-[0_8px_28px_rgba(16,28,44,0.08)]">
                  <span className="text-lg font-semibold tracking-[-0.02em] text-cream">{c.name}</span>
                  <span className="text-sm text-mist">{c.sector}</span>
                </Panel>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
