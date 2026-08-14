"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { DualAxisStamp } from "@/components/brand/dual-axis-stamp";
import { Select } from "@/components/ui/field";
import { EmptyState, ErrorState, Badge } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Panel } from "@/components/ui/panel";
import { api, type StartupCard } from "@/lib/api";

export default function DealflowPage() {
  const [items, setItems] = useState<StartupCard[] | null>(null);
  const [watching, setWatching] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [sector, setSector] = useState("");
  const [stage, setStage] = useState("");
  const [country, setCountry] = useState("");

  async function load() {
    setError(null);
    setItems(null);
    try {
      const qs = new URLSearchParams();
      if (sector) qs.set("sector", sector);
      if (stage) qs.set("stage", stage);
      if (country) qs.set("country", country);
      const q = qs.toString();
      const [page, watch] = await Promise.all([api.discover(q ? `?${q}` : ""), api.getWatchlist().catch(() => ({ startup_ids: [] as string[] }))]);
      setItems(page.items);
      setWatching(new Set(watch.startup_ids));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load dealflow.");
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sector, stage, country]);

  return (
    <div className="space-y-6">
      <PageHeader title="Dealflow" description="Summary tier only. Full reports open at the meeting." />
      <Panel className="grid gap-3 md:grid-cols-3">
        <Select label="Sector" value={sector} onChange={(e) => setSector(e.target.value)}>
          <option value="">Any</option>
          <option>Fintech</option>
          <option>Healthtech</option>
          <option>SaaS / B2B</option>
          <option>Climate</option>
        </Select>
        <Select label="Stage" value={stage} onChange={(e) => setStage(e.target.value)}>
          <option value="">Any</option>
          <option value="pre_seed">Pre-seed</option>
          <option value="seed">Seed</option>
          <option value="series_a">Series A</option>
          <option value="growth">Growth</option>
        </Select>
        <Select label="Country" value={country} onChange={(e) => setCountry(e.target.value)}>
          <option value="">Any</option>
          <option value="NG">Nigeria</option>
          <option value="GH">Ghana</option>
          <option value="KE">Kenya</option>
          <option value="ZA">South Africa</option>
          <option value="GB">United Kingdom</option>
          <option value="US">United States</option>
        </Select>
      </Panel>
      {error ? (
        <ErrorState message={error} onRetry={() => void load()} />
      ) : items === null ? (
        <PageSkeleton rows={4} />
      ) : items.length === 0 ? (
        <EmptyState title="No cards match" body="Widen the filters, or wait for more published audits." />
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {items.map((c) => (
            <li key={c.startup_id}>
              <Link href={`/investor/company/${c.startup_id}`} className="block">
                <Panel className="transition-shadow hover:shadow-[0_8px_28px_rgba(16,28,44,0.08)]">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-xl font-semibold tracking-[-0.02em] text-cream">{c.name ?? "Unnamed"}</h2>
                        {watching.has(c.startup_id) ? <Badge tone="brass">Watching</Badge> : null}
                      </div>
                      <p className="mt-1 text-sm text-mist">
                        {c.sector} · {c.stage} · {c.country}
                      </p>
                    </div>
                    <DualAxisStamp fundability={c.fundability} saleability={c.saleability} size={96} />
                  </div>
                </Panel>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
