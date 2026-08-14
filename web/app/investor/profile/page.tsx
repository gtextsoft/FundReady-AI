"use client";

import Link from "next/link";
import { PageHeader } from "@/components/ui/page-header";
import { Badge, ErrorState } from "@/components/ui/states";
import { MetaList, MetaRow, Panel } from "@/components/ui/panel";
import { PageSkeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { humanize } from "@/lib/format";
import { useSession } from "@/stores/session";
import { useLoad } from "@/lib/hooks/use-load";

export default function InvestorProfilePage() {
  const session = useSession((s) => s.session);
  const load = useLoad(() => api.getInvestorMe(), []);

  if (load.status === "loading") return <PageSkeleton />;
  if (load.status === "error") return <ErrorState message={load.message} onRetry={() => void load.reload()} />;

  const thesis = load.status === "ready" ? load.data : null;
  const status = thesis?.review_status ?? "none";
  const linkLabel =
    status === "accepted" ? "View thesis →" : status === "in_review" ? "Thesis in review →" : "Submit thesis →";

  return (
    <div className="max-w-xl space-y-6">
      <PageHeader title="Account" />
      <Panel>
        <MetaList>
          <MetaRow label="Name">{session?.displayName}</MetaRow>
          <MetaRow label="Email">
            <span className="block">{session?.email}</span>
            <span className="text-xs text-mist">{session?.emailVerified ? "Confirmed" : "Unconfirmed"}</span>
          </MetaRow>
          <MetaRow label="Thesis">
            <Badge
              tone={status === "accepted" ? "pass" : status === "in_review" ? "hold" : status === "rejected" ? "fail" : "mist"}
            >
              {humanize(status)}
            </Badge>
          </MetaRow>
        </MetaList>
      </Panel>
      <Link href="/investor/verify" className="text-sm font-semibold text-brand">
        {linkLabel}
      </Link>
    </div>
  );
}
