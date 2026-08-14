"use client";

import Link from "next/link";
import { useState } from "react";
import { Select } from "@/components/ui/field";
import { Badge, EmptyState, ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Panel, PanelList, PanelRow } from "@/components/ui/panel";
import { api, type ProfileResponse } from "@/lib/api";
import { humanize } from "@/lib/format";
import { useLoad } from "@/lib/hooks/use-load";

export default function AdminStartupsPage() {
  const [status, setStatus] = useState("");
  const load = useLoad(
    async () => {
      const qs = status ? `?company_verification_status=${status}` : "";
      const p = await api.listStartups(qs);
      return p.items;
    },
    [status],
    (d) => d.length === 0,
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Startups" />
      <Panel className="max-w-xs">
        <Select label="Verification" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Any</option>
          <option value="none">None</option>
          <option value="submitted">Submitted</option>
          <option value="in_review">In review</option>
          <option value="accepted">Accepted</option>
          <option value="rejected">Rejected</option>
        </Select>
      </Panel>
      {load.status === "loading" ? <PageSkeleton /> : null}
      {load.status === "error" ? <ErrorState message={load.message} onRetry={() => void load.reload()} /> : null}
      {load.status === "empty" ? <EmptyState title="No startups" body="Nothing matches this filter." /> : null}
      {load.status === "ready" ? (
        <PanelList>
          {load.data.map((s: ProfileResponse) => (
            <PanelRow key={s.id} className="p-0">
              <Link href={`/admin/startups/${s.id}`} className="flex items-center justify-between px-4 py-3.5">
                <div>
                  <p className="text-lg font-semibold tracking-[-0.02em] text-cream">{s.name ?? "Untitled"}</p>
                  <p className="text-sm text-mist">
                    {s.sector} · {s.country} · {s.investor_visible ? "published" : "unpublished"}
                  </p>
                </div>
                <Badge tone={s.company_verification_status === "accepted" ? "pass" : "mist"}>
                  {humanize(s.company_verification_status)}
                </Badge>
              </Link>
            </PanelRow>
          ))}
        </PanelList>
      ) : null}
    </div>
  );
}
