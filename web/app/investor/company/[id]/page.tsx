"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { DualAxisStamp } from "@/components/brand/dual-axis-stamp";
import { Button } from "@/components/ui/button";
import { Field, TextArea } from "@/components/ui/field";
import { LockedCard, ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Panel } from "@/components/ui/panel";
import { api, type Interest, type StartupCard } from "@/lib/api";
import { investorGate, gateCopy } from "@/lib/domain/access";
import { investorAccount } from "@/lib/format";
import { useSession } from "@/stores/session";
import { toast } from "sonner";

export default function CompanyPage() {
  const { id } = useParams<{ id: string }>();
  const session = useSession((s) => s.session);
  const [card, setCard] = useState<StartupCard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [slot, setSlot] = useState("");
  const [interest, setInterest] = useState<Interest | null>(null);
  const [watching, setWatching] = useState(false);
  const [busy, setBusy] = useState<"watch" | "interest" | "call" | null>(null);
  const g = investorGate(investorAccount(session), "expressInterest");

  async function load() {
    setError(null);
    try {
      const [c, list, watch] = await Promise.all([
        api.discoverOne(id),
        api.listInterests(),
        api.getWatchlist().catch(() => ({ startup_ids: [] as string[] })),
      ]);
      setCard(c);
      setInterest(list.find((i) => i.startup_id === id) ?? null);
      setWatching(watch.startup_ids.includes(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load this card.");
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!card) return <PageSkeleton />;

  const copy = gateCopy(g.reason, "investor");

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
      <div className="space-y-6">
        <PageHeader
          eyebrow="Summary tier"
          title={card.name ?? "Unnamed"}
          description={`${card.sector} · ${card.stage} · ${card.country}`}
        />
        <p className="max-w-xl text-sm text-mist">
          Financials, findings, and founder contact are not on this card. Express interest and SACI
          decides whether a meeting — and a reveal — follows.
        </p>
        <div className="flex flex-wrap gap-3">
          <Button
            type="button"
            variant="ghost"
            loading={busy === "watch"}
            onClick={async () => {
              setBusy("watch");
              try {
                const res = await api.toggleWatch(id);
                setWatching(res.watching ?? !watching);
                toast.success(res.watching ?? !watching ? "Added to watchlist." : "Removed from watchlist.");
              } catch (err) {
                toast.error(err instanceof Error ? err.message : "Could not update watchlist.");
              } finally {
                setBusy(null);
              }
            }}
          >
            {watching ? "Watching" : "Watch"}
          </Button>
          <Button href={`/investor/company/${id}/analyst`} variant="quiet">
            Ask the analyst
          </Button>
        </div>
        {!g.allowed ? (
          <LockedCard title={copy.title} body={copy.body} cta={copy.cta} href="/verify-email" />
        ) : (
          <Panel className="space-y-4">
            <TextArea
              label="Note for SACI (the founder never sees this)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <Button
              type="button"
              disabled={Boolean(interest)}
              loading={busy === "interest"}
              onClick={async () => {
                setBusy("interest");
                try {
                  const row = await api.expressInterest(id, note);
                  setInterest(row);
                  toast.success("Interest filed.");
                } catch (err) {
                  toast.error(err instanceof Error ? err.message : "Could not file interest.");
                } finally {
                  setBusy(null);
                }
              }}
            >
              {interest ? `Interest ${interest.status}` : "Express interest"}
            </Button>
            {interest ? (
              <>
                <Field
                  label="Propose a call (local time)"
                  type="datetime-local"
                  value={slot}
                  onChange={(e) => setSlot(e.target.value)}
                />
                <Button
                  type="button"
                  variant="ghost"
                  disabled={!slot}
                  loading={busy === "call"}
                  onClick={async () => {
                    if (!slot) {
                      toast.error("Choose a slot first.");
                      return;
                    }
                    setBusy("call");
                    try {
                      await api.requestCall(interest.id, new Date(slot).toISOString());
                      toast.success("Call proposed.");
                    } catch (err) {
                      toast.error(err instanceof Error ? err.message : "Could not propose a call.");
                    } finally {
                      setBusy(null);
                    }
                  }}
                >
                  Request call
                </Button>
              </>
            ) : null}
          </Panel>
        )}
      </div>
      <Panel as="aside" className="flex justify-center lg:sticky lg:top-20">
        <DualAxisStamp fundability={card.fundability} saleability={card.saleability} />
      </Panel>
    </div>
  );
}
