"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge, EmptyState, ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Panel, PanelList, PanelRow, SectionLabel } from "@/components/ui/panel";
import { api, type DocumentRow, type InvestorReviewCard, type ProfileResponse } from "@/lib/api";
import { humanize } from "@/lib/format";
import { useLoad } from "@/lib/hooks/use-load";
import { toast } from "sonner";

type StartupRow = { startup: ProfileResponse; documents: DocumentRow[] };

export default function VerificationsPage() {
  const load = useLoad(
    async () => {
      const [theses, page, submitted] = await Promise.all([
        api.listInvestorTheses("?review_status=in_review&limit=100"),
        api.listStartups("?company_verification_status=in_review&limit=100"),
        api.listStartups("?company_verification_status=submitted&limit=100"),
      ]);
      const startups = [...page.items, ...submitted.items];
      const rows: StartupRow[] = [];
      for (const s of startups) {
        const docs = await api.listDocuments(s.id).catch(() => ({ items: [] as DocumentRow[] }));
        rows.push({ startup: s, documents: docs.items });
      }
      return { theses: theses.items, companies: rows };
    },
    [],
    (d) => d.theses.length === 0 && d.companies.length === 0,
  );
  const [busyId, setBusyId] = useState<string | null>(null);

  if (load.status === "loading") return <PageSkeleton />;
  if (load.status === "error") return <ErrorState message={load.message} onRetry={() => void load.reload()} />;
  if (load.status === "empty") {
    return (
      <div className="space-y-6">
        <PageHeader title="Verifications" description="Investor theses and founder registration certificates awaiting a decision." />
        <EmptyState title="Nothing waiting" body="Submitted investor theses and company certificates appear here for accept or reject." />
      </div>
    );
  }

  const theses = load.data.theses;
  const companies = load.data.companies;

  async function decideThesis(row: InvestorReviewCard, accept: boolean) {
    const key = `${row.user_id}-${accept ? "yes" : "no"}`;
    setBusyId(key);
    try {
      await api.decideThesisReview(row.user_id, accept);
      toast.success(accept ? "Thesis accepted." : "Thesis rejected.");
      await load.reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not decide.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-10">
      <PageHeader title="Verifications" description="Investor theses and founder registration certificates awaiting a decision." />

      <section className="space-y-3">
        <SectionLabel>Investor theses</SectionLabel>
        {theses.length === 0 ? (
          <Panel>
            <p className="text-sm text-mist">No theses in review.</p>
          </Panel>
        ) : (
          <PanelList>
            {theses.map((row) => {
              const name = [row.first_name, row.last_name].filter(Boolean).join(" ") || row.email;
              return (
                <PanelRow key={row.user_id}>
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <p className="text-lg font-semibold tracking-[-0.02em] text-cream">{name}</p>
                      <p className="text-sm text-mist">
                        {row.firm ?? "No firm"} · {row.investor_type ?? "—"} · {row.country ?? "—"}
                      </p>
                      <p className="mt-1 text-sm text-mist">
                        {(row.thesis_sectors[0] ?? "Any sector") + " · " + (row.thesis_stages[0] ? humanize(row.thesis_stages[0]) : "Any stage")}
                      </p>
                      {row.risk_notes ? <p className="mt-2 max-w-xl text-sm text-cream">{row.risk_notes}</p> : null}
                      <div className="mt-2">
                        <Badge tone="hold">{humanize(row.review_status)}</Badge>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        type="button"
                        loading={busyId === `${row.user_id}-yes`}
                        onClick={() => void decideThesis(row, true)}
                      >
                        Accept
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        loading={busyId === `${row.user_id}-no`}
                        onClick={() => void decideThesis(row, false)}
                      >
                        Reject
                      </Button>
                    </div>
                  </div>
                </PanelRow>
              );
            })}
          </PanelList>
        )}
      </section>

      <section className="space-y-3">
        <SectionLabel>Company certificates</SectionLabel>
        {companies.length === 0 ? (
          <Panel>
            <p className="text-sm text-mist">No certificates waiting.</p>
          </Panel>
        ) : (
          <PanelList>
            {companies.map(({ startup: s, documents }) => (
              <PanelRow key={s.id}>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="text-lg font-semibold tracking-[-0.02em] text-cream">{s.name ?? "Untitled"}</p>
                    <p className="text-sm text-mist">
                      {s.country} · {s.sector}
                    </p>
                    <div className="mt-2">
                      <Badge tone="hold">{humanize(s.company_verification_status)}</Badge>
                    </div>
                    <ul className="mt-3 space-y-1 rounded-[12px] bg-rail px-3 py-2 text-sm text-mist">
                      {documents.length === 0 ? <li>No file listed yet.</li> : null}
                      {documents.map((d) => (
                        <li key={d.id}>
                          {d.filename} · {humanize(d.kind)} · {humanize(d.status)}
                        </li>
                      ))}
                    </ul>
                    <Link href={`/admin/startups/${s.id}`} className="mt-2 inline-block text-sm font-semibold text-brand">
                      Open dossier →
                    </Link>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      loading={busyId === `${s.id}-yes`}
                      onClick={async () => {
                        setBusyId(`${s.id}-yes`);
                        try {
                          await api.decideCompanyVerification(s.id, true);
                          toast.success("Accepted.");
                          await load.reload();
                        } catch (err) {
                          toast.error(err instanceof Error ? err.message : "Could not accept.");
                        } finally {
                          setBusyId(null);
                        }
                      }}
                    >
                      Accept
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      loading={busyId === `${s.id}-no`}
                      onClick={async () => {
                        setBusyId(`${s.id}-no`);
                        try {
                          await api.decideCompanyVerification(s.id, false);
                          toast.success("Rejected.");
                          await load.reload();
                        } catch (err) {
                          toast.error(err instanceof Error ? err.message : "Could not reject.");
                        } finally {
                          setBusyId(null);
                        }
                      }}
                    >
                      Reject
                    </Button>
                  </div>
                </div>
              </PanelRow>
            ))}
          </PanelList>
        )}
      </section>
    </div>
  );
}
