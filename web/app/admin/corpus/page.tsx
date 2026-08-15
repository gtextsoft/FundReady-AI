"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/field";
import { Badge, EmptyState, ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Panel, PanelList, PanelRow } from "@/components/ui/panel";
import { api, queryString, type CorpusPage } from "@/lib/api";
import { humanize } from "@/lib/format";
import { useLoad } from "@/lib/hooks/use-load";
import { toast } from "sonner";

const PAGE_SIZE = 50;

function saveJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function AdminCorpusPage() {
  const [status, setStatus] = useState("");
  const [country, setCountry] = useState("");
  const [sector, setSector] = useState("");
  const [stage, setStage] = useState("");
  const [published, setPublished] = useState("");
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const filters = {
    company_verification_status: status || undefined,
    country: country.trim().length === 2 ? country.trim() : undefined,
    sector: sector.trim() || undefined,
    stage: stage || undefined,
    published: published === "" ? undefined : published === "yes",
  };
  const load = useLoad(
    async () => {
      return api.exportCorpus(queryString({ ...filters, limit: PAGE_SIZE, offset }));
    },
    [status, country, sector, stage, published, offset],
    (d) => d.total === 0,
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Training corpus"
        description="Identity-stripped scored files for later model training. Legal names, registration numbers, founder contacts, and emails are removed. Each export is audit-logged."
      />
      <Panel className="grid gap-3 md:grid-cols-3">
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
      </Panel>
      {load.status === "loading" ? <PageSkeleton /> : null}
      {load.status === "error" ? <ErrorState message={load.message} onRetry={() => void load.reload()} /> : null}
      {load.status === "empty" ? (
        <EmptyState title="No records" body="Nothing matches these filters yet." />
      ) : null}
      {load.status === "ready" ? (
        <CorpusResults
          page={load.data}
          offset={offset}
          busy={busy}
          onPage={setOffset}
          onDownloadPage={() => {
            saveJson(`fundready-corpus-${new Date().toISOString().slice(0, 10)}.json`, load.data);
            toast.success(`Downloaded ${load.data.items.length} records.`);
          }}
          onDownloadAll={async () => {
            setBusy(true);
            try {
              const items = [];
              let cursor = 0;
              let total = 0;
              do {
                const page = await api.exportCorpus(
                  queryString({ ...filters, limit: 200, offset: cursor }),
                );
                items.push(...page.items);
                total = page.total;
                cursor += 200;
              } while (items.length < total);
              saveJson(`fundready-corpus-all-${new Date().toISOString().slice(0, 10)}.json`, {
                items,
                total,
                purpose: "model_training",
              });
              toast.success(`Downloaded ${items.length} records.`);
            } catch (err) {
              toast.error(err instanceof Error ? err.message : "Could not export.");
            } finally {
              setBusy(false);
            }
          }}
        />
      ) : null}
    </div>
  );
}

function CorpusResults({
  page,
  offset,
  busy,
  onPage,
  onDownloadPage,
  onDownloadAll,
}: {
  page: CorpusPage;
  offset: number;
  busy: boolean;
  onPage: (next: number) => void;
  onDownloadPage: () => void;
  onDownloadAll: () => Promise<void>;
}) {
  const from = page.total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + page.items.length, page.total);
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-mist tabular-nums">
          {from}–{to} of {page.total} · {page.purpose.replace("_", " ")}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="ghost" onClick={onDownloadPage}>
            Download this page
          </Button>
          <Button type="button" loading={busy} onClick={() => void onDownloadAll()}>
            Download all matching
          </Button>
        </div>
      </div>
      <PanelList>
        {page.items.map((row) => (
          <PanelRow key={row.startup_id} className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm text-cream tabular-nums">{row.startup_id.slice(0, 8)}</p>
              <p className="text-[11px] text-mist">
                {row.sector ?? "—"} · {row.stage ?? "—"} · {row.country ?? "—"} ·{" "}
                {row.published ? "published" : "unpublished"}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge tone={row.latest_audit ? "pass" : "hold"}>{row.latest_audit ? "audit" : "no audit"}</Badge>
              <Badge tone="mist">{row.tasks.length} tasks</Badge>
              <Badge tone={row.verification === "accepted" ? "pass" : "mist"}>{humanize(row.verification)}</Badge>
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
