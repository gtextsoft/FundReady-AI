"use client";

import { useEffect, useState } from "react";
import { MentorDesk, type MentorTurn } from "@/components/mentor/mentor-desk";
import { Button } from "@/components/ui/button";
import { EmptyState, LockedCard } from "@/components/ui/states";
import { PageSkeleton } from "@/components/ui/skeleton";
import { api, type AuditReport, type AuditRun, type ReadinessSummary, type ReadinessTask } from "@/lib/api";
import { gate, gateCopy } from "@/lib/domain/access";
import { founderAccount } from "@/lib/format";
import { useStartup } from "@/lib/hooks/use-startup";
import { useSession } from "@/stores/session";

type Briefing = {
  run: AuditRun | null;
  report: AuditReport | null;
  summary: ReadinessSummary | null;
  tasks: ReadinessTask[];
};

async function loadBriefing(startupId: string): Promise<Briefing> {
  const [runs, summary, taskPage] = await Promise.all([
    api.listAudits(startupId),
    api.getTasksSummary(startupId).catch(() => null),
    api.listTasks(startupId).catch(() => ({ items: [] as ReadinessTask[] })),
  ]);
  const run = runs[0] ?? null;
  const succeeded = runs.find((r) => r.status === "succeeded") ?? null;
  const report = succeeded ? await api.getAuditReport(startupId, succeeded.id) : null;
  return { run, report, summary, tasks: taskPage.items };
}

function MentorChrome({ children }: { children: React.ReactNode }) {
  return (
    <div className="space-y-6">
      <div>
        <p className="text-[10px] font-extrabold tracking-[0.16em] text-text-faint uppercase">Briefing</p>
        <h1 className="mt-1.5 font-display text-[32px] leading-none font-medium tracking-[-0.03em] text-cream italic">
          Your file is open.
        </h1>
        <p className="mt-2 max-w-xl text-sm text-mist">
          The mentor only answers from your audit and task list. Nothing else.
        </p>
      </div>
      {children}
    </div>
  );
}

export default function MentorPage() {
  const session = useSession((s) => s.session);
  const { profile, loading } = useStartup();
  const g = gate(founderAccount(session, profile?.company_verification_status), "aiMentor");
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [briefingError, setBriefingError] = useState<string | null>(null);
  const [history, setHistory] = useState<MentorTurn[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!profile || !g.allowed) return;
    let stop = false;
    void (async () => {
      try {
        const next = await loadBriefing(profile.id);
        if (!stop) {
          setBriefing(next);
          setBriefingError(null);
        }
      } catch (err) {
        if (!stop) setBriefingError(err instanceof Error ? err.message : "Could not open the file.");
      }
    })();
    return () => {
      stop = true;
    };
  }, [profile, g.allowed]);

  if (loading) return <PageSkeleton />;
  if (!g.allowed) {
    const copy = gateCopy(g.reason, "founder");
    return (
      <MentorChrome>
        <LockedCard
          title={copy.title}
          body={copy.body}
          cta={copy.cta}
          href={g.reason === "payment" ? "/founder/paywall" : "/verify-email"}
        />
      </MentorChrome>
    );
  }
  if (!profile) {
    return (
      <MentorChrome>
        <EmptyState
          title="No company on file"
          body="Complete intake so the mentor has a company to brief against."
          action={<Button href="/onboarding">Start intake</Button>}
        />
      </MentorChrome>
    );
  }
  if (briefingError) {
    return (
      <MentorChrome>
        <EmptyState
          title="Could not open the file"
          body={briefingError}
          action={
            <Button
              type="button"
              onClick={() => {
                setBriefingError(null);
                void loadBriefing(profile.id)
                  .then(setBriefing)
                  .catch((err) => setBriefingError(err instanceof Error ? err.message : "Could not open the file."));
              }}
            >
              Try again
            </Button>
          }
        />
      </MentorChrome>
    );
  }
  if (!briefing) return <PageSkeleton rows={4} />;

  if (!briefing.report) {
    const running = briefing.run?.status === "queued" || briefing.run?.status === "running";
    const failed = briefing.run?.status === "failed";
    return (
      <MentorChrome>
        <EmptyState
          title={running ? "The report is still landing." : failed ? "The last audit did not finish." : "No audit on file."}
          body={
            running
              ? "The mentor opens when the assessment completes. Check results in a moment."
              : "Run a successful audit first. There is nothing to ground answers in yet."
          }
          action={
            <Button href={running ? "/results" : "/assessment"}>
              {running ? "Watch the audit" : "Run assessment"}
            </Button>
          }
        />
      </MentorChrome>
    );
  }

  return (
    <MentorDesk
      profile={profile}
      report={briefing.report}
      summary={briefing.summary}
      tasks={briefing.tasks}
      history={history}
      busy={busy}
      onReset={() => setHistory([])}
      onSend={async (message) => {
        const userTurn: MentorTurn = { id: crypto.randomUUID(), role: "user", content: message };
        const assistantId = crypto.randomUUID();
        const next: MentorTurn[] = [...history, userTurn, { id: assistantId, role: "assistant", content: "" }];
        setHistory(next);
        setBusy(true);
        try {
          const res = await api.chatMentorStream(
            profile.id,
            message,
            [...history, userTurn]
              .filter((t) => t.role !== "system")
              .map((t) => ({ role: t.role, content: t.content })),
            (text) => {
              setHistory((prev) =>
                prev.map((t) => (t.id === assistantId ? { ...t, content: t.content + text } : t)),
              );
            },
          );
          setHistory((prev) =>
            prev.map((t) =>
              t.id === assistantId
                ? { ...t, content: res.reply || t.content, citations: res.citations }
                : t,
            ),
          );
        } catch (err) {
          setHistory((prev) => [
            ...prev.filter((t) => t.id !== assistantId),
            {
              id: crypto.randomUUID(),
              role: "system",
              content: err instanceof Error ? err.message : "The mentor could not answer.",
            },
          ]);
        } finally {
          setBusy(false);
        }
      }}
    />
  );
}
