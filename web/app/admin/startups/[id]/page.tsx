"use client";

import { useParams } from "next/navigation";
import { PaperReport } from "@/components/brand/paper-report";
import { Button } from "@/components/ui/button";
import { Badge, ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { PanelList, PanelRow } from "@/components/ui/panel";
import { api, type AuditReport, type AuditRun, type ProfileResponse } from "@/lib/api";
import { humanize } from "@/lib/format";
import { useLoad } from "@/lib/hooks/use-load";
import { toast } from "sonner";

export default function AdminStartupDossier() {
  const { id } = useParams<{ id: string }>();
  const load = useLoad(async () => {
    const profile = await api.getProfileById(id);
    const runs = await api.listAudits(id);
    const ok = runs.find((r) => r.status === "succeeded");
    const report = ok ? await api.getAdminAuditReport(id, ok.id) : null;
    return { profile, runs, report };
  }, [id]);

  if (load.status === "loading") return <PageSkeleton rows={4} />;
  if (load.status === "error" || load.status === "empty") {
    return <ErrorState message={load.status === "error" ? load.message : "Not found."} onRetry={() => void load.reload()} />;
  }

  const { profile, runs, report } = load.data as {
    profile: ProfileResponse;
    runs: AuditRun[];
    report: AuditReport | null;
  };

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Admin dossier"
        title={profile.name ?? "Untitled"}
        description={`${profile.sector} · ${profile.country} · ${humanize(profile.company_verification_status)}`}
      />
      {report ? <PaperReport report={report} /> : <p className="text-mist">No succeeded audit yet.</p>}
      <PanelList>
        {runs.map((r) => (
          <PanelRow key={r.id} className="flex items-center justify-between text-sm">
            <div>
              <p className="text-xs text-mist tabular-nums">{r.id.slice(0, 8)}</p>
              <p className="text-cream">{new Date(r.created_at).toLocaleString()}</p>
            </div>
            <Badge tone={r.status === "succeeded" ? "pass" : r.status === "failed" ? "fail" : "hold"}>
              {humanize(r.status)}
            </Badge>
          </PanelRow>
        ))}
      </PanelList>
      <Button
        type="button"
        variant="ghost"
        onClick={async () => {
          const tasks = await api.listTasks(id, "?status=failed");
          const locked = tasks.items.find((t) => t.attempts_remaining === 0);
          if (!locked) {
            toast.message("No locked failed task.");
            return;
          }
          await api.reopenTask(locked.id);
          toast.success("Task reopened.");
        }}
      >
        Reopen a locked task
      </Button>
    </div>
  );
}
