"use client";

import { useEffect, useState } from "react";
import { DualAxisStamp } from "@/components/brand/dual-axis-stamp";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LockedCard } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Panel, SectionLabel } from "@/components/ui/panel";
import { api, type AuditReport, type AuditRun, type Product, type ReadinessSummary } from "@/lib/api";
import { daysLeftInTrial, gate, gateCopy, hasAccess } from "@/lib/domain/access";
import { founderAccount } from "@/lib/format";
import { useStartup } from "@/lib/hooks/use-startup";
import { useSession } from "@/stores/session";
import { toast } from "sonner";

export default function FounderHome() {
  const session = useSession((s) => s.session);
  const { profile, loading, error, reload } = useStartup();
  const [summary, setSummary] = useState<ReadinessSummary | null>(null);
  const [report, setReport] = useState<AuditReport | null>(null);
  const [run, setRun] = useState<AuditRun | null>(null);
  const [deskError, setDeskError] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [recs, setRecs] = useState<Product[]>([]);

  useEffect(() => {
    if (!profile) return;
    void (async () => {
      try {
        const s = await api.getTasksSummary(profile.id);
        setSummary(s);
        const runs = await api.listAudits(profile.id);
        const latest = runs[0];
        setRun(latest ?? null);
        if (latest?.status === "succeeded") {
          setReport(await api.getAuditReport(profile.id, latest.id));
        }
        const recPage = await api.listRecommendations(profile.id).catch(() => null);
        setRecs(recPage?.items ?? []);
        setDeskError(null);
      } catch (err) {
        setDeskError(err instanceof Error ? err.message : "Could not load desk details.");
      }
    })();
  }, [profile]);

  if (loading) return <PageSkeleton />;
  if (error) return <ErrorState message={error} onRetry={() => void reload()} />;
  if (!profile) {
    return (
      <EmptyState
        title="No company on file"
        body="Complete intake so the audit has something to score."
        action={<Button href="/onboarding">Start intake</Button>}
      />
    );
  }

  const account = founderAccount(session, profile.company_verification_status);
  const paid = hasAccess(account);
  const days = daysLeftInTrial(account);
  const vis = gate(account, "investorVisibility");
  const copy = gateCopy(vis.reason, "founder");
  const floor = summary?.publish_floor ?? 50;
  const fundScore = report?.fundability.score ?? summary?.fundability_score ?? null;
  const scoreCleared = summary?.score_cleared ?? (fundScore !== null && fundScore >= floor);
  const live = Boolean(summary?.discoverable);
  const nextLabel = !run
    ? "Run the audit"
    : run.status === "queued" || run.status === "running"
      ? "Audit in flight"
      : !scoreCleared
        ? "Not ready to go live"
        : summary && summary.required_open > 0
          ? `${summary.required_open} required tasks open`
          : live
            ? "Live in dealflow"
            : "Publish when ready";

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Founder desk"
        title={profile.name ?? "Untitled company"}
        description={`${profile.sector ?? "Sector unset"} · ${profile.country ?? "Country unset"}`}
        action={
          report ? (
            <DualAxisStamp fundability={report.fundability} saleability={report.saleability} size={140} />
          ) : null
        }
      />

      {!session?.emailVerified ? (
        <LockedCard
          title="Confirm your email"
          body="Needed before you can publish, talk to the mentor, or take investor requests."
          cta="Confirm email"
          href="/verify-email"
        />
      ) : null}
      {!paid ? (
        <LockedCard
          title="Trial ended"
          body="One payment restores full access."
          cta="View unlock"
          href="/founder/paywall"
        />
      ) : session?.subscriptionStatus !== "active" ? (
        <Panel className="bg-rail-promo">
          <p className="text-sm text-mist">
            Trial: <span className="font-semibold text-cream">{days} days</span> remaining.{" "}
            <Button href="/founder/billing" variant="quiet" size="sm" className="px-0">
              Billing
            </Button>
          </p>
        </Panel>
      ) : (
        <p className="text-sm text-mist">
          Access unlocked.{" "}
          <Button href="/founder/billing" variant="quiet" size="sm" className="px-0">
            Billing
          </Button>
        </p>
      )}

      {deskError ? <ErrorState message={deskError} onRetry={() => void reload()} /> : null}

      <div className="grid gap-4 md:grid-cols-3">
        <Panel>
          <SectionLabel>Next</SectionLabel>
          <p className="mt-2 text-lg font-semibold tracking-[-0.02em] text-cream">
            {nextLabel}
          </p>
          <div className="mt-4">
            {!run || !scoreCleared ? (
              <Button href={!run ? "/assessment" : "/onboarding"} variant="quiet" size="sm" className="px-0">
                {!run ? "Queue assessment →" : "Update review →"}
              </Button>
            ) : summary && summary.required_open > 0 ? (
              <Button href="/founder/tasks" variant="quiet" size="sm" className="px-0">
                Open readiness →
              </Button>
            ) : (
              <Button href="/results" variant="quiet" size="sm" className="px-0">
                Read the report →
              </Button>
            )}
          </div>
        </Panel>
        <Panel>
          <SectionLabel>Fundability</SectionLabel>
          <p className="mt-2 text-lg font-semibold tracking-[-0.02em] text-cream">
            {fundScore === null ? "No score yet" : `${fundScore}%`}
          </p>
          <p className="mt-2 text-sm text-mist">
            {scoreCleared
              ? `At or above the ${floor}% go-live bar.`
              : `Investors need ${floor}% or higher. Update the review and re-run the assessment.`}
          </p>
        </Panel>
        <Panel>
          <SectionLabel>Dealflow</SectionLabel>
          <p className="mt-2 text-lg font-semibold tracking-[-0.02em] text-cream">
            {live ? "Live with investors" : profile.investor_visible ? "Opted in — not listed yet" : "Not live"}
          </p>
          {!scoreCleared ? (
            <div className="mt-3 space-y-3">
              <p className="text-sm text-mist">
                This company is not ready for funding yet. Update the latest review so AI can re-audit. You can go live once the score is {floor}% or higher.
              </p>
              <div className="flex flex-wrap gap-3">
                <Button href="/onboarding" variant="ghost" size="sm">
                  Update review
                </Button>
                <Button href="/assessment" variant="quiet" size="sm" className="px-0">
                  Re-run assessment →
                </Button>
              </div>
              {profile.investor_visible ? (
                <Button
                  variant="quiet"
                  size="sm"
                  className="px-0"
                  loading={publishing}
                  onClick={async () => {
                    setPublishing(true);
                    try {
                      await api.unpublish(profile.id);
                      toast.success("Unpublished.");
                      await reload();
                    } catch (err) {
                      toast.error(err instanceof Error ? err.message : "Could not unpublish.");
                    } finally {
                      setPublishing(false);
                    }
                  }}
                >
                  Unpublish
                </Button>
              ) : null}
            </div>
          ) : vis.allowed ? (
            <Button
              className="mt-4"
              variant="ghost"
              loading={publishing}
              onClick={async () => {
                setPublishing(true);
                try {
                  if (profile.investor_visible) await api.unpublish(profile.id);
                  else await api.publish(profile.id);
                  toast.success(profile.investor_visible ? "Unpublished." : "Published to dealflow.");
                  await reload();
                } catch (err) {
                  toast.error(err instanceof Error ? err.message : "Could not update visibility.");
                } finally {
                  setPublishing(false);
                }
              }}
            >
              {profile.investor_visible ? "Unpublish" : "Go live"}
            </Button>
          ) : (
            <p className="mt-3 text-sm text-mist">{copy.body}</p>
          )}
        </Panel>
      </div>

      {recs.length > 0 ? (
        <Panel>
          <SectionLabel>Recommended next</SectionLabel>
          <ul className="mt-3 space-y-2">
            {recs.slice(0, 3).map((item) => (
              <li key={item.id} className="text-sm text-cream">
                {item.title}
                <span className="ml-2 text-mist">{item.kind}</span>
              </li>
            ))}
          </ul>
          <Button href="/founder/programmes" variant="quiet" size="sm" className="mt-3 px-0">
            Browse programmes →
          </Button>
        </Panel>
      ) : null}
    </div>
  );
}
