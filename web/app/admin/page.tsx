"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, TextArea } from "@/components/ui/field";
import { Badge, EmptyState, ErrorState } from "@/components/ui/states";
import { ConfirmDialog } from "@/components/ui/dialog";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { PanelList, PanelRow } from "@/components/ui/panel";
import { api, type AdminStats, type Interest, type Meeting } from "@/lib/api";
import { formatSlot } from "@/lib/utils";
import { humanize } from "@/lib/format";
import { useLoad } from "@/lib/hooks/use-load";
import { toast } from "sonner";

function QueueRow({
  item,
  name,
  onChanged,
}: {
  item: Interest;
  name: string;
  onChanged: () => Promise<void>;
}) {
  const [when, setWhen] = useState("");
  const [location, setLocation] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [revealOpen, setRevealOpen] = useState(false);
  const [meetings, setMeetings] = useState<Meeting[]>([]);

  useEffect(() => {
    if (item.status !== "approved") return;
    void api.listMeetings(item.id).then(setMeetings).catch(() => setMeetings([]));
  }, [item.id, item.status]);

  return (
    <PanelRow>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-lg font-semibold tracking-[-0.02em] text-cream">{name}</p>
          {item.note ? <p className="mt-1 text-sm text-mist">{item.note}</p> : null}
          <p className="mt-2 text-[11px] text-mist tabular-nums">{new Date(item.created_at).toLocaleString()}</p>
        </div>
        <Badge tone={item.status === "approved" ? "pass" : item.status === "declined" ? "fail" : "hold"}>
          {humanize(item.status)}
        </Badge>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {item.status === "pending" ? (
          <>
            <Button
              type="button"
              loading={busy === "approve"}
              onClick={async () => {
                setBusy("approve");
                try {
                  await api.approveInterest(item.id);
                  toast.success("Approved.");
                  await onChanged();
                } catch (err) {
                  toast.error(err instanceof Error ? err.message : "Could not approve.");
                } finally {
                  setBusy(null);
                }
              }}
            >
              Approve
            </Button>
            <Button
              type="button"
              variant="ghost"
              loading={busy === "decline"}
              onClick={async () => {
                setBusy("decline");
                try {
                  await api.declineInterest(item.id);
                  toast.success("Declined.");
                  await onChanged();
                } catch (err) {
                  toast.error(err instanceof Error ? err.message : "Could not decline.");
                } finally {
                  setBusy(null);
                }
              }}
            >
              Decline
            </Button>
          </>
        ) : null}
        {item.status === "approved" ? (
          <>
            <Button type="button" variant="danger" onClick={() => setRevealOpen(true)}>
              Reveal report
            </Button>
            <div className="mt-3 w-full rounded-[14px] bg-rail p-4">
              <div className="grid gap-3 md:grid-cols-2">
                <Field
                  label="Meeting (local)"
                  type="datetime-local"
                  value={when}
                  onChange={(e) => setWhen(e.target.value)}
                  className="min-w-56"
                />
                <Field label="Location" value={location} onChange={(e) => setLocation(e.target.value)} />
                <TextArea label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} className="md:col-span-2" />
              </div>
              <Button
                type="button"
                variant="ghost"
                className="mt-3"
                disabled={!when}
                loading={busy === "meet"}
                onClick={async () => {
                  if (!when) {
                    toast.error("Choose a meeting time.");
                    return;
                  }
                  setBusy("meet");
                  try {
                    const row = await api.scheduleMeeting(item.id, {
                      scheduled_at: new Date(when).toISOString(),
                      duration_minutes: 45,
                      location: location || undefined,
                      notes: notes || undefined,
                    });
                    setMeetings((prev) => [row, ...prev]);
                    toast.success("Meeting booked.");
                    setWhen("");
                    setLocation("");
                    setNotes("");
                  } catch (err) {
                    toast.error(err instanceof Error ? err.message : "Could not book.");
                  } finally {
                    setBusy(null);
                  }
                }}
              >
                Schedule meeting
              </Button>
              {meetings.length ? (
                <ul className="mt-4 space-y-2 text-sm text-mist">
                  {meetings.map((m) => (
                    <li key={m.id} className="flex flex-wrap items-center justify-between gap-2">
                      <span>
                        {formatSlot(m.scheduled_at)} · {humanize(m.status)}
                        {m.location ? ` · ${m.location}` : ""}
                      </span>
                      {m.status === "proposed" ? (
                        <Button
                          type="button"
                          variant="ghost"
                          loading={busy === `confirm-${m.id}`}
                          onClick={async () => {
                            setBusy(`confirm-${m.id}`);
                            try {
                              const row = await api.confirmMeeting(item.id, m.id, {
                                location: location || undefined,
                                notes: notes || undefined,
                              });
                              setMeetings((prev) => prev.map((x) => (x.id === row.id ? row : x)));
                              toast.success("Meeting confirmed.");
                            } catch (err) {
                              toast.error(err instanceof Error ? err.message : "Could not confirm.");
                            } finally {
                              setBusy(null);
                            }
                          }}
                        >
                          Confirm
                        </Button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </>
        ) : null}
      </div>
      <ConfirmDialog
        open={revealOpen}
        title="Reveal the full report?"
        body="This is logged. The investor will be able to open the complete audit."
        confirmLabel="Reveal report"
        danger
        busy={busy === "reveal"}
        onClose={() => setRevealOpen(false)}
        onConfirm={async () => {
          setBusy("reveal");
          try {
            const res = await api.revealInterest(item.id);
            toast.success(`Revealed run ${res.audit_run_id.slice(0, 8)}`);
            setRevealOpen(false);
            await onChanged();
          } catch (err) {
            toast.error(err instanceof Error ? err.message : "Could not reveal.");
          } finally {
            setBusy(null);
          }
        }}
      />
    </PanelRow>
  );
}

function StatsStrip({ stats }: { stats: AdminStats }) {
  const cards = [
    { href: "/admin/startups", label: "Startups", value: stats.startups_total },
    { href: "/admin/startups", label: "Published", value: stats.startups_published },
    { href: "/admin/corpus", label: "Audited", value: stats.startups_with_succeeded_audit },
    { href: "/admin/users", label: "Founders", value: stats.users_founders },
    { href: "/admin/users", label: "Investors", value: stats.users_investors },
    { href: "/admin", label: "Pending interest", value: stats.interests_pending },
  ];
  return (
    <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {cards.map((card) => (
        <li key={card.label}>
          <Link href={card.href} className="block rounded-[18px] bg-rail-active px-4 py-3 ring-1 ring-black/5 dark:ring-white/10">
            <p className="text-[10px] font-extrabold tracking-[0.16em] text-text-faint uppercase">{card.label}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums tracking-[-0.03em] text-cream">{card.value}</p>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export default function AdminQueuePage() {
  const load = useLoad(
    async () => {
      const [list, startups, stats] = await Promise.all([
        api.listInterests(),
        api.listStartups("?limit=100"),
        api.adminStats(),
      ]);
      const names: Record<string, string> = {};
      for (const s of startups.items) names[s.id] = s.name ?? s.id.slice(0, 8);
      return { items: list, names, stats };
    },
    [],
  );

  if (load.status === "loading") return <PageSkeleton />;
  if (load.status === "error") return <ErrorState message={load.message} onRetry={() => void load.reload()} />;
  if (load.status !== "ready") return null;

  return (
    <div className="space-y-6">
      <PageHeader title="Interest queue" description="Approval is not a reveal. Reveal is a separate, logged action." />
      <StatsStrip stats={load.data.stats} />
      {load.data.items.length === 0 ? (
        <EmptyState title="Empty queue" body="Investor interest arrives here, oldest first on the server." />
      ) : (
        <PanelList>
          {load.data.items.map((i) => (
            <QueueRow key={i.id} item={i} name={load.data.names[i.startup_id] ?? i.startup_id.slice(0, 8)} onChanged={load.reload} />
          ))}
        </PanelList>
      )}
    </div>
  );
}
