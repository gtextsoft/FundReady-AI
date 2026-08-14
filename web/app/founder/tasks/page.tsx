"use client";

import { useEffect, useState } from "react";
import { Badge, EmptyState, ErrorState } from "@/components/ui/states";
import { Button } from "@/components/ui/button";
import { FileField } from "@/components/ui/file-field";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Panel, PanelList, PanelRow, SectionLabel } from "@/components/ui/panel";
import { api, putFile, type ReadinessSummary, type ReadinessTask } from "@/lib/api";
import { humanize } from "@/lib/format";
import { useStartup } from "@/lib/hooks/use-startup";
import { toast } from "sonner";

export default function TasksPage() {
  const { profile, loading, error, reload } = useStartup();
  const [tasks, setTasks] = useState<ReadinessTask[] | null>(null);
  const [summary, setSummary] = useState<ReadinessSummary | null>(null);
  const [selected, setSelected] = useState<ReadinessTask | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  async function load(id: string) {
    try {
      const [list, sum] = await Promise.all([api.listTasks(id), api.getTasksSummary(id)]);
      setTasks(list.items);
      setSummary(sum);
      setListError(null);
      setSelected((cur) => list.items.find((t) => t.id === cur?.id) ?? list.items[0] ?? null);
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Could not load tasks.");
    }
  }

  useEffect(() => {
    if (profile) void load(profile.id);
  }, [profile]);

  async function upload(task: ReadinessTask, file: File) {
    try {
      const ticket = await api.beginEvidence(task.id, {
        filename: file.name,
        content_type: file.type || "application/octet-stream",
      });
      await putFile(ticket.upload_url, file);
      await api.completeEvidence(ticket.evidence_id);
      toast.success("Evidence submitted. Grading is in the queue.");
      if (profile) await load(profile.id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed.");
    }
  }

  if (loading) return <PageSkeleton />;
  if (error) return <ErrorState message={error} onRetry={() => void reload()} />;
  if (!profile) {
    return (
      <EmptyState
        title="No profile"
        body="Complete intake first."
        action={<Button href="/onboarding">Start intake</Button>}
      />
    );
  }
  if (listError) return <ErrorState message={listError} onRetry={() => void load(profile.id)} />;
  if (!tasks) return <PageSkeleton />;
  if (tasks.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Readiness" title="Prove the work." />
        <EmptyState title="No tasks yet" body="Run an audit. The action plan becomes this list." />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Readiness"
        title="Prove the work."
        description={
          summary
            ? `${summary.required_open} required still open · ${summary.required_passed} passed`
            : undefined
        }
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <PanelList role="listbox" aria-label="Tasks">
          {tasks.map((t) => (
            <PanelRow key={t.id} active={selected?.id === t.id} className="p-0">
              <button
                type="button"
                role="option"
                aria-selected={selected?.id === t.id}
                onClick={() => setSelected(t)}
                className="flex min-h-14 w-full cursor-pointer items-start justify-between gap-4 px-4 py-3.5 text-left"
              >
                <div>
                  <p className="text-sm text-cream">{t.action}</p>
                  <p className="mt-1 text-[11px] tracking-wider text-mist uppercase">
                    {t.dimension.replace(/_/g, " ")}
                  </p>
                </div>
                <Badge
                  tone={
                    t.status === "passed" ? "pass" : t.status === "failed" ? "fail" : t.is_priority ? "hold" : "mist"
                  }
                >
                  {humanize(t.status)}
                </Badge>
              </button>
            </PanelRow>
          ))}
        </PanelList>
        <Panel as="aside" className="lg:sticky lg:top-20">
          {selected ? (
            <>
              <SectionLabel>{humanize(selected.requirement)}</SectionLabel>
              <p className="mt-2 text-sm text-cream">{selected.action}</p>
              <p className="mt-3 text-xs text-mist">Attempts remaining: {selected.attempts_remaining}</p>
              <div className="mt-6">
                <FileField
                  label="Upload evidence"
                  hint="PDF or image. File is sent as soon as you choose it."
                  accept=".pdf,.png,.jpg,.jpeg,.webp"
                  onFile={(file) => upload(selected, file)}
                />
              </div>
            </>
          ) : (
            <p className="text-sm text-mist">Select a task.</p>
          )}
        </Panel>
      </div>
    </div>
  );
}
