"use client";

import { useParams } from "next/navigation";
import { PaperReport } from "@/components/brand/paper-report";
import { ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useLoad } from "@/lib/hooks/use-load";

export default function RevealedReportPage() {
  const { interestId, runId } = useParams<{ interestId: string; runId: string }>();
  const load = useLoad(() => api.getRevealedReport(interestId, runId), [interestId, runId]);

  if (load.status === "loading") return <PageSkeleton rows={4} />;
  if (load.status === "error" || load.status === "empty") {
    return (
      <div className="space-y-4">
        <ErrorState message={load.status === "error" ? load.message : "Not revealed."} onRetry={() => void load.reload()} />
        <Button href="/investor/interests" variant="ghost">
          Back to interests
        </Button>
      </div>
    );
  }

  return (
    <div className="max-w-3xl">
      <PageHeader
        eyebrow="SACI reveal"
        title="Full report"
        description="Opened by a SACI admin. This path does not exist without a reveal record."
      />
      <div className="mt-6">
        <PaperReport report={load.data} />
      </div>
    </div>
  );
}
