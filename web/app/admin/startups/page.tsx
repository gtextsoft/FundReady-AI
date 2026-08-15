"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/field";
import { Badge, EmptyState, ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Panel, PanelList, PanelRow } from "@/components/ui/panel";
import { api, queryString, type Page, type ProfileResponse } from "@/lib/api";
import { humanize } from "@/lib/format";
import { useLoad } from "@/lib/hooks/use-load";

const PAGE_SIZE = 20;

export default function AdminStartupsPage() {
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState("");
  const [status, setStatus] = useState("");
  const [country, setCountry] = useState("");
  const [sector, setSector] = useState("");
  const [stage, setStage] = useState("");
  const [published, setPublished] = useState("");
  const [offset, setOffset] = useState(0);
  const load = useLoad(
    async () => {
      return api.listStartups(
        queryString({
          q: applied || undefined,
          company_verification_status: status || undefined,
          country: country.trim().length === 2 ? country.trim() : undefined,
          sector: sector.trim() || undefined,
          stage: stage || undefined,
          published: published === "" ? undefined : published === "yes",
          limit: PAGE_SIZE,
          offset,
        }),
      );
    },
    [applied, status, country, sector, stage, published, offset],
    (d) => d.total === 0,
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Startups"
        description="Search and page the full catalogue. Open a row for the dossier, or export scored files from Corpus."
      />
      <Panel className="grid gap-3 md:grid-cols-3">
        <Field
          label="Search"
          placeholder="Name, sector, country"
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
          label="Verification"
          value={status}
          onChange={(e) => {
            setOffset(0);
            setStatus(e.target.value);
          }}
        >
          <option value="">Any</option>
          <option value="none">None</option>
          <option value="submitted">Submitted</option>
          <option value="in_review">In review</option>
          <option value="accepted">Accepted</option>
          <option value="rejected">Rejected</option>
        </Select>
        <Select
          label="Stage"
          value={stage}
          onChange={(e) => {
            setOffset(0);
            setStage(e.target.value);
          }}
        >
          <option value="">Any</option>
          <option value="idea">idea</option>
          <option value="pre_seed">pre_seed</option>
          <option value="seed">seed</option>
          <option value="series_a">series_a</option>
          <option value="series_b_plus">series_b_plus</option>
          <option value="growth">growth</option>
        </Select>
        <Field
          label="Country"
          placeholder="NG"
          maxLength={2}
          value={country}
          onChange={(e) => {
            setOffset(0);
            setCountry(e.target.value.toUpperCase());
          }}
        />
        <Field
          label="Sector"
          placeholder="fintech"
          value={sector}
          onChange={(e) => {
            setOffset(0);
            setSector(e.target.value);
          }}
        />
        <Select
          label="Published"
          value={published}
          onChange={(e) => {
            setOffset(0);
            setPublished(e.target.value);
          }}
        >
          <option value="">Any</option>
          <option value="yes">Published</option>
          <option value="no">Unpublished</option>
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
      {load.status === "loading" ? <PageSkeleton /> : null}
      {load.status === "error" ? <ErrorState message={load.message} onRetry={() => void load.reload()} /> : null}
      {load.status === "empty" ? <EmptyState title="No startups" body="Nothing matches these filters." /> : null}
      {load.status === "ready" ? <StartupResults page={load.data} offset={offset} onPage={setOffset} /> : null}
    </div>
  );
}

function StartupResults({
  page,
  offset,
  onPage,
}: {
  page: Page<ProfileResponse>;
  offset: number;
  onPage: (next: number) => void;
}) {
  const from = page.total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + page.items.length, page.total);
  return (
    <>
      <p className="text-sm text-mist tabular-nums">
        {from}–{to} of {page.total}
      </p>
      <PanelList>
        {page.items.map((s) => (
          <PanelRow key={s.id} className="p-0">
            <Link href={`/admin/startups/${s.id}`} className="flex items-center justify-between px-4 py-3.5">
              <div>
                <p className="text-lg font-semibold tracking-[-0.02em] text-cream">{s.name ?? "Untitled"}</p>
                <p className="text-sm text-mist">
                  {s.sector} · {s.country} · {s.stage} · {s.investor_visible ? "published" : "unpublished"}
                </p>
              </div>
              <Badge tone={s.company_verification_status === "accepted" ? "pass" : "mist"}>
                {humanize(s.company_verification_status)}
              </Badge>
            </Link>
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
