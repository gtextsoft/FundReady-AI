"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PaperReport } from "@/components/brand/paper-report";
import { BrandMark } from "@/components/brand/mark";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/states";
import { PageSkeleton } from "@/components/ui/skeleton";
import { api, type AuditReport, type AuditRun } from "@/lib/api";
import { ApiFailure } from "@/lib/api/errors";
import { founderNeedsOnboarding } from "@/lib/domain/onboarding";
import { toast } from "sonner";

export default function ResultsPage() {
  const [run, setRun] = useState<AuditRun | null>(null);
  const [report, setReport] = useState<AuditReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    let stop = false;
    async function load() {
      try {
        const profile = await api.getProfile();
        if (founderNeedsOnboarding(profile)) {
          router.replace("/onboarding");
          return;
        }
        const runs = await api.listAudits(profile.id);
        const latest = runs[0];
        if (stop) return;
        setRun(latest ?? null);
        if (latest?.status === "succeeded") {
          setReport(await api.getAuditReport(profile.id, latest.id));
        }
        setError(null);
      } catch (err) {
        if (!stop) {
          if (err instanceof ApiFailure && err.code === "not_found") {
            router.replace("/onboarding");
            return;
          }
          setError(err instanceof Error ? err.message : "Could not load the report.");
        }
      } finally {
        if (!stop) setLoading(false);
      }
    }
    void load();
    const id = setInterval(() => {
      void (async () => {
        try {
          const profile = await api.getProfile();
          const runs = await api.listAudits(profile.id);
          const latest = runs[0];
          if (stop) return;
          setRun(latest ?? null);
          if (latest?.status === "succeeded") {
            setReport(await api.getAuditReport(profile.id, latest.id));
            clearInterval(id);
          }
          if (latest?.status === "failed") clearInterval(id);
        } catch (err) {
          if (err instanceof ApiFailure && err.code === "not_found") {
            clearInterval(id);
            router.replace("/onboarding");
          }
        }
      })();
    }, 3000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [router]);

  async function downloadPdf() {
    if (!run) return;
    try {
      const profile = await api.getProfile();
      const bytes = await api.getAuditPdf(profile.id, run.id);
      const copy = new Uint8Array(bytes.byteLength);
      copy.set(bytes);
      const blob = new Blob([copy], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "fundready-audit.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not download the PDF.");
    }
  }

  return (
    <div id="main" tabIndex={-1} className="min-h-dvh bg-bg px-6 py-10">
      <div className="mx-auto max-w-3xl">
        <BrandMark />
        <h1 className="mt-8 font-display text-4xl text-cream">The verdict.</h1>
        {loading && !report ? <div className="mt-8"><PageSkeleton rows={4} /></div> : null}
        {error ? (
          <div className="mt-6">
            <ErrorState message={error} />
            <Button href="/assessment" className="mt-4">
              Re-run assessment
            </Button>
          </div>
        ) : null}
        {run?.status === "failed" ? (
          <div className="mt-6 space-y-4">
            <p className="text-sm text-fail">{run.error_message ?? "The audit failed."}</p>
            <Button href="/assessment">Try again</Button>
          </div>
        ) : null}
        {run && (run.status === "queued" || run.status === "running") ? (
          <p className="mt-6 text-mist">Still running. This page will not invent a score.</p>
        ) : null}
        {!loading && !run && !error ? (
          <div className="mt-6 space-y-4">
            <p className="text-sm text-mist">No audit on file yet.</p>
            <Button href="/assessment">Queue assessment</Button>
          </div>
        ) : null}
        {report ? (
          <div className="mt-8">
            <PaperReport report={report} />
            <div className="mt-6 flex flex-wrap gap-3">
              <Button type="button" variant="ghost" onClick={() => void downloadPdf()}>
                Download PDF
              </Button>
              <Button href="/founder">Go to dashboard</Button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
