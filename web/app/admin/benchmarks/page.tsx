"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/field";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Panel, PanelList, PanelRow } from "@/components/ui/panel";
import { api, type Benchmark } from "@/lib/api";
import { useLoad } from "@/lib/hooks/use-load";
import { toast } from "sonner";

export default function BenchmarksPage() {
  const [sector, setSector] = useState("");
  const [stage, setStage] = useState("seed");
  const [metric, setMetric] = useState("gross_margin_percent");
  const [region, setRegion] = useState("NG");
  const [p25, setP25] = useState("");
  const [p50, setP50] = useState("");
  const [p75, setP75] = useState("");
  const [source, setSource] = useState("");
  const [asOf, setAsOf] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useLoad(
    async () => {
      return api.listBenchmarks();
    },
    [],
    (d) => d.length === 0,
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Benchmarks" description="The yardstick every verdict is measured against. Retired, never deleted." />
      <Panel className="grid gap-3 md:grid-cols-3">
        <Field label="Sector" value={sector} onChange={(e) => setSector(e.target.value)} />
        <Select label="Stage" value={stage} onChange={(e) => setStage(e.target.value)}>
          <option value="idea">idea</option>
          <option value="pre_seed">pre_seed</option>
          <option value="seed">seed</option>
          <option value="series_a">series_a</option>
          <option value="growth">growth</option>
        </Select>
        <Field label="Metric" value={metric} onChange={(e) => setMetric(e.target.value)} />
        <Field label="Region" value={region} onChange={(e) => setRegion(e.target.value)} />
        <Field label="p25" type="number" value={p25} onChange={(e) => setP25(e.target.value)} />
        <Field label="p50" type="number" value={p50} onChange={(e) => setP50(e.target.value)} />
        <Field label="p75" type="number" value={p75} onChange={(e) => setP75(e.target.value)} />
        <Field label="Source" value={source} onChange={(e) => setSource(e.target.value)} />
        <Field label="As of" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
        {formError ? <p className="text-sm text-fail md:col-span-3">{formError}</p> : null}
        <Button
          type="button"
          loading={busy}
          onClick={async () => {
            if (!sector.trim() || !p25 || !p50 || !p75 || !asOf) {
              setFormError("Sector, percentiles, and as-of date are required.");
              return;
            }
            setFormError(null);
            setBusy(true);
            try {
              await api.createBenchmark({
                sector,
                stage,
                metric,
                region,
                p25,
                p50,
                p75,
                source,
                as_of_date: asOf,
              });
              toast.success("Benchmark stored.");
              await load.reload();
            } catch (err) {
              toast.error(err instanceof Error ? err.message : "Could not store.");
            } finally {
              setBusy(false);
            }
          }}
        >
          Create
        </Button>
      </Panel>
      {load.status === "loading" ? <PageSkeleton /> : null}
      {load.status === "error" ? <ErrorState message={load.message} onRetry={() => void load.reload()} /> : null}
      {load.status === "empty" ? <EmptyState title="No benchmarks" body="Create the first yardstick above." /> : null}
      {load.status === "ready" ? (
        <PanelList>
          {load.data.map((b: Benchmark) => (
            <PanelRow key={b.id} className="flex items-center justify-between gap-3 text-sm">
              <span className="text-cream">
                {b.sector} · {b.stage} · {b.metric} · {b.region}
              </span>
              <span className="text-xs text-mist tabular-nums">
                {b.p25} / {b.p50} / {b.p75}
              </span>
              {b.is_active ? (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={async () => {
                    await api.retireBenchmark(b.id);
                    await load.reload();
                  }}
                >
                  Retire
                </Button>
              ) : (
                <span className="text-mist">retired</span>
              )}
            </PanelRow>
          ))}
        </PanelList>
      ) : null}
    </div>
  );
}
