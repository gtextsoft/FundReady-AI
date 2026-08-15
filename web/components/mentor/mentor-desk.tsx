"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ArrowUp, CircleAlert, ListChecks, TrendingUp } from "lucide-react";
import { Mark } from "@/components/brand/mark";
import { Button } from "@/components/ui/button";
import { PANEL_RING, PANEL_SHADOW, SectionLabel } from "@/components/ui/panel";
import { humanize } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AuditReport, ProfileResponse, ReadinessSummary, ReadinessTask } from "@/lib/api";

export type MentorTurn = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations?: { kind: string; ref: string }[];
};

const AGENDA = [
  {
    icon: ListChecks,
    label: "Highest leverage",
    prompt: "What is the highest-leverage task on my plan?",
  },
  {
    icon: CircleAlert,
    label: "Sharpest finding",
    prompt: "Which finding should I fix first?",
  },
  {
    icon: TrendingUp,
    label: "Investor read",
    prompt: "How do investors read my traction?",
  },
] as const;

function verdictLabel(level: string | undefined) {
  const known: Record<string, string> = {
    ready: "Ready",
    fundable: "Fundable",
    saleable: "Saleable",
    not_yet: "Not yet",
    provisional: "Provisional",
    insufficient_data: "Thin data",
  };
  if (!level) return "—";
  return known[level] ?? humanize(level);
}

function citationLabel(kind: string, ref: string) {
  const cleaned = ref.replace(/^(finding|task|verdict|profile):/i, "").replace(/[_-]+/g, " ");
  return `${humanize(kind)} · ${humanize(cleaned)}`;
}

function openTasks(tasks: ReadinessTask[]) {
  return tasks
    .filter((t) => t.status === "open" || t.status === "failed" || t.status === "needs_more")
    .sort((a, b) => Number(b.is_priority) - Number(a.is_priority))
    .slice(0, 3);
}

function topFindings(report: AuditReport | null) {
  if (!report) return [];
  const rank = (s: string) => (s === "certain" ? 0 : s === "likely" ? 1 : 2);
  return [...report.findings].sort((a, b) => rank(a.severity) - rank(b.severity)).slice(0, 2);
}

export function MentorDesk({
  profile,
  report,
  summary,
  tasks,
  history,
  busy,
  onSend,
  onReset,
}: {
  profile: ProfileResponse;
  report: AuditReport | null;
  summary: ReadinessSummary | null;
  tasks: ReadinessTask[];
  history: MentorTurn[];
  busy: boolean;
  onSend: (message: string) => Promise<void>;
  onReset: () => void;
}) {
  const [draft, setDraft] = useState("");
  const scrollerRef = useRef<HTMLDivElement>(null);
  const inputId = useId();
  const pending = openTasks(tasks);
  const findings = topFindings(report);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollTo({ top: el.scrollHeight, behavior: reduce ? "auto" : "smooth" });
  }, [history, busy]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setDraft("");
    await onSend(trimmed);
  }

  return (
    <div className="flex min-h-[calc(100dvh-8.5rem)] flex-col gap-5 lg:h-[calc(100dvh-8.5rem)]">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[10px] font-extrabold tracking-[0.16em] text-text-faint uppercase">Briefing</p>
          <h1 className="mt-1.5 font-display text-[32px] leading-none font-medium tracking-[-0.03em] text-cream italic">
            Your file is open.
          </h1>
          <p className="mt-2 max-w-xl text-sm text-mist">
            Ask about a blocker, a score, or what to prove next. Answers stay inside your audit and task list.
          </p>
        </div>
        {history.length > 0 ? (
          <Button type="button" variant="ghost" size="sm" onClick={onReset}>
            New briefing
          </Button>
        ) : null}
      </header>

      <div className="grid min-h-0 flex-1 gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <section
          className={cn(
            "flex min-h-[520px] flex-col overflow-hidden rounded-[22px] bg-rail-active lg:min-h-0",
            PANEL_SHADOW,
            PANEL_RING,
          )}
        >
          <div
            ref={scrollerRef}
            className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5 sm:px-6"
            aria-live="polite"
            aria-label="Mentor conversation"
          >
            {history.length === 0 && !busy ? (
              <EmptyBriefing onPick={(prompt) => void send(prompt)} />
            ) : (
              <>
                {history.map((turn) => (
                  <TurnBubble key={turn.id} turn={turn} />
                ))}
                {busy && !history.some((t) => t.role === "assistant" && t.content) ? (
                  <TypingIndicator />
                ) : null}
              </>
            )}
          </div>

          <form
            className="border-t border-black/5 p-3 sm:p-4 dark:border-white/10"
            onSubmit={(e) => {
              e.preventDefault();
              void send(draft);
            }}
          >
            <div className="flex items-end gap-2 rounded-[16px] bg-white p-2 ring-1 ring-black/5 dark:bg-surface-2 dark:ring-white/10">
              <label htmlFor={inputId} className="sr-only">
                Message
              </label>
              <textarea
                id={inputId}
                rows={2}
                value={draft}
                disabled={busy}
                placeholder="Ask about the gap that is costing you the meeting."
                className="min-h-11 w-full resize-none bg-transparent px-3 py-2.5 text-[16px] text-cream outline-none placeholder:text-mist-2 sm:text-[14px]"
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send(draft);
                  }
                }}
              />
              <button
                type="submit"
                disabled={busy || !draft.trim()}
                aria-label="Send message"
                className="mb-0.5 inline-flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center rounded-full bg-brand text-brand-ink transition-colors duration-200 hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-40"
              >
                <ArrowUp size={18} strokeWidth={2.4} />
              </button>
            </div>
            <p className="mt-2 px-1 text-[11px] text-text-faint">Enter to send · Shift+Enter for a new line</p>
          </form>
        </section>

        <Dossier
          profile={profile}
          report={report}
          summary={summary}
          pending={pending}
          findings={findings}
          onAsk={(prompt) => void send(prompt)}
        />
      </div>
    </div>
  );
}

function EmptyBriefing({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <div className="flex h-full min-h-[420px] flex-col justify-center">
      <p className="font-display text-[26px] leading-tight font-medium tracking-[-0.03em] text-cream italic sm:text-[30px]">
        What should we prove before the next meeting?
      </p>
      <p className="mt-3 max-w-md text-sm text-mist">Pick an agenda item, or type your own. The mentor will not invent facts outside this file.</p>
      <ul className="mt-8 grid gap-2">
        {AGENDA.map((item) => (
          <li key={item.prompt}>
            <button
              type="button"
              onClick={() => onPick(item.prompt)}
              className="flex min-h-14 w-full cursor-pointer items-center gap-4 rounded-[16px] bg-rail px-4 py-3 text-left ring-1 ring-black/5 transition-colors duration-200 hover:bg-rail-hover hover:ring-brand/25 dark:ring-white/10"
            >
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-rail-promo text-brand">
                <item.icon size={18} />
              </span>
              <span>
                <span className="block text-[10px] font-extrabold tracking-[0.16em] text-text-faint uppercase">
                  {item.label}
                </span>
                <span className="mt-0.5 block text-sm text-cream">{item.prompt}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TurnBubble({ turn }: { turn: MentorTurn }) {
  if (turn.role === "system") {
    return (
      <div role="alert" className="rounded-[16px] border-l-2 border-fail bg-fail/5 px-4 py-3">
        <p className="text-[10px] font-extrabold tracking-[0.16em] text-fail uppercase">Notice</p>
        <p className="mt-1 text-sm leading-relaxed text-fail">{turn.content}</p>
      </div>
    );
  }

  if (turn.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[min(100%,36rem)] rounded-[18px] rounded-br-[6px] bg-brand px-4 py-3 text-sm leading-relaxed text-brand-ink">
          <p className="whitespace-pre-wrap">{turn.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3">
      <Mark size={28} className="mt-0.5 shrink-0" />
      <div className="min-w-0 max-w-[min(100%,36rem)]">
        <p className="text-[10px] font-extrabold tracking-[0.16em] text-text-faint uppercase">Mentor</p>
        <p className="mt-1 text-sm leading-relaxed whitespace-pre-wrap text-cream">{turn.content}</p>
        {turn.citations?.length ? (
          <ul className="mt-3 flex flex-wrap gap-1.5">
            {turn.citations.map((c) => (
              <li
                key={`${c.kind}:${c.ref}`}
                className="rounded-full bg-rail-promo px-2.5 py-1 text-[11px] font-medium text-brand"
              >
                {citationLabel(c.kind, c.ref)}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-3" aria-label="Mentor is writing">
      <Mark size={28} />
      <div className="flex gap-1.5 rounded-[16px] bg-rail px-3.5 py-3">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-1.5 w-1.5 rounded-full bg-brand"
            style={{ animation: "fr-dots 1s ease-in-out infinite", animationDelay: `${i * 160}ms` }}
          />
        ))}
      </div>
    </div>
  );
}

function Dossier({
  profile,
  report,
  summary,
  pending,
  findings,
  onAsk,
}: {
  profile: ProfileResponse;
  report: AuditReport | null;
  summary: ReadinessSummary | null;
  pending: ReadinessTask[];
  findings: AuditReport["findings"];
  onAsk: (prompt: string) => void;
}) {
  const fund = report?.fundability;
  const sale = report?.saleability;

  return (
    <aside
      className={cn(
        "overflow-hidden rounded-[22px] bg-rail-active lg:min-h-0 lg:overflow-y-auto",
        PANEL_SHADOW,
        PANEL_RING,
      )}
    >
      <div className="h-1.5 bg-brand" aria-hidden />
      <div className="space-y-5 p-5">
        <div>
          <SectionLabel>On file</SectionLabel>
          <p className="mt-2 font-display text-[22px] leading-tight font-medium tracking-[-0.02em] text-cream">
            {profile.name ?? "Untitled company"}
          </p>
          <p className="mt-1 text-sm text-mist">
            {[profile.sector, humanize(profile.stage), profile.country].filter(Boolean).join(" · ") || "Profile incomplete"}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <ScoreCell label="Fundability" score={fund?.score ?? null} level={fund?.level} />
          <ScoreCell label="Saleability" score={sale?.score ?? null} level={sale?.level} />
        </div>

        <div>
          <SectionLabel>Readiness</SectionLabel>
          <p className="mt-2 text-sm text-cream">
            {summary
              ? summary.gate_cleared
                ? "Gate cleared. You can publish when you choose."
                : `${summary.required_open} required ${summary.required_open === 1 ? "task" : "tasks"} still open.`
              : "No task list yet."}
          </p>
        </div>

        {pending.length > 0 ? (
          <div>
            <SectionLabel>Still to prove</SectionLabel>
            <ul className="mt-2 divide-y divide-black/5 dark:divide-white/10">
              {pending.map((task) => (
                <li key={task.id}>
                  <button
                    type="button"
                    onClick={() => onAsk(`How should I prove this: ${task.action}`)}
                    className="flex min-h-11 w-full cursor-pointer py-2.5 text-left text-sm text-cream transition-colors duration-200 hover:text-brand"
                  >
                    {task.action}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {findings.length > 0 ? (
          <div>
            <SectionLabel>On the report</SectionLabel>
            <ul className="mt-2 space-y-2">
              {findings.map((f) => (
                <li key={f.code}>
                  <button
                    type="button"
                    onClick={() => onAsk(`Explain this finding in plain language: ${f.message}`)}
                    className="min-h-11 w-full cursor-pointer rounded-[12px] bg-rail px-3 py-2.5 text-left transition-colors duration-200 hover:bg-rail-hover"
                  >
                    <span className="text-[10px] font-extrabold tracking-[0.16em] text-text-faint uppercase">
                      {humanize(f.severity)}
                    </span>
                    <span className="mt-0.5 block text-sm text-cream">{f.message}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <p className="text-[11px] leading-relaxed text-text-faint">
          The mentor cannot see other companies, investor notes, or anything you have not put on this file.
        </p>
      </div>
    </aside>
  );
}

function ScoreCell({
  label,
  score,
  level,
}: {
  label: string;
  score: number | null;
  level?: string;
}) {
  return (
    <div className="rounded-[14px] bg-rail px-3 py-3">
      <p className="text-[10px] font-extrabold tracking-[0.16em] text-text-faint uppercase">{label}</p>
      <p className="mt-1 font-display text-[28px] leading-none text-cream">
        {score == null ? "—" : Math.round(score)}
      </p>
      <p className="mt-1.5 text-[11px] text-mist">{verdictLabel(level)}</p>
    </div>
  );
}
