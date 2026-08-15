"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { PanelList, PanelRow } from "@/components/ui/panel";
import { api, type NotificationItem } from "@/lib/api";
import { relativeTime } from "@/lib/utils";
import { useSession } from "@/stores/session";

function hrefFor(n: NotificationItem, role: string | undefined): string | null {
  const p = n.payload ?? {};
  if (n.kind.includes("meeting")) {
    if (role === "founder") return "/founder/requests";
    if (role === "investor") return "/investor/interests";
    return "/admin";
  }
  if (typeof p.startup_id === "string") return `/investor/company/${p.startup_id}`;
  if (typeof p.task_id === "string") return "/founder/tasks";
  if (n.kind.includes("call") || n.kind.includes("request")) return "/founder/requests";
  if (n.kind.includes("audit")) return "/results";
  if (n.kind.includes("interest")) return "/investor/interests";
  return null;
}

export function AlertsInbox({ emptyBody }: { emptyBody: string }) {
  const role = useSession((s) => s.session?.role);
  const [items, setItems] = useState<NotificationItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const page = await api.listNotifications();
      setItems(page.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load alerts.");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function markVisible() {
    if (!items) return;
    const unread = items.filter((n) => !n.read_at).map((n) => n.id);
    if (unread.length) {
      try {
        await api.markRead(unread);
      } catch {
        /* badge poll will catch up */
      }
    }
  }

  useEffect(() => {
    if (!items) return;
    const id = window.setTimeout(() => void markVisible(), 1200);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!items) return <PageSkeleton />;
  if (items.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader title="Alerts" />
        <EmptyState title="Quiet desk" body={emptyBody} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Alerts" description="Newest first. Unread items clear shortly after you open this page." />
      <PanelList>
        {items.map((n) => {
          const href = hrefFor(n, role);
          const inner = (
            <>
              <div className="flex justify-between gap-4">
                <p className="text-sm font-medium text-cream">{n.title}</p>
                <span className="text-[11px] text-mist tabular-nums">{relativeTime(n.created_at)}</span>
              </div>
              <p className="mt-1 text-sm text-mist">{n.body}</p>
            </>
          );
          return (
            <PanelRow key={n.id} active={!n.read_at}>
              {href ? (
                <Link href={href} className="block hover:text-brand">
                  {inner}
                </Link>
              ) : (
                inner
              )}
            </PanelRow>
          );
        })}
      </PanelList>
    </div>
  );
}
