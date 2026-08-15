"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LockedCard } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Panel, SectionLabel } from "@/components/ui/panel";
import { api, type Enrolment, type Product } from "@/lib/api";
import { gate, gateCopy } from "@/lib/domain/access";
import { founderAccount } from "@/lib/format";
import { formatMoney } from "@/lib/utils";
import { useLoad } from "@/lib/hooks/use-load";
import { useSession } from "@/stores/session";
import { toast } from "sonner";

export default function ProgrammesPage() {
  const session = useSession((s) => s.session);
  const g = gate(founderAccount(session), "programmes");
  const load = useLoad(
    async () => {
      const [p, enrolments] = await Promise.all([api.listProducts(), api.listEnrolments()]);
      return {
        products: p.items.filter((x) => x.active),
        enrolments: enrolments.items,
      };
    },
    [],
    (d) => d.products.length === 0 && d.enrolments.length === 0,
  );
  const [busyId, setBusyId] = useState<string | null>(null);

  if (!g.allowed) {
    const copy = gateCopy(g.reason, "founder");
    return (
      <LockedCard
        title={copy.title}
        body={copy.body}
        cta={copy.cta}
        href={g.reason === "payment" ? "/founder/paywall" : "/verify-email"}
      />
    );
  }

  if (load.status === "loading") return <PageSkeleton />;
  if (load.status === "error") return <ErrorState message={load.message} onRetry={() => void load.reload()} />;
  if (load.status === "empty") {
    return (
      <div className="space-y-6">
        <PageHeader title="Programmes" description="Matched to gaps when the audit names them. Enrolment is optional." />
        <EmptyState title="No programmes listed" body="SACI has not published catalogue items yet." />
      </div>
    );
  }

  const enrolledIds = new Set(load.data.enrolments.map((e: Enrolment) => e.product_id));

  return (
    <div className="space-y-8">
      <PageHeader title="Programmes" description="Matched to gaps when the audit names them. Enrolment is optional." />
      {load.data.enrolments.length ? (
        <section className="space-y-3">
          <SectionLabel>Your enrolments</SectionLabel>
          <ul className="space-y-2 text-sm text-mist">
            {load.data.enrolments.map((e: Enrolment) => (
              <li key={e.id}>{e.product?.title ?? "Catalogue item"} · {new Date(e.created_at).toLocaleDateString()}</li>
            ))}
          </ul>
        </section>
      ) : null}
      <ul className="grid gap-4 md:grid-cols-2">
        {load.data.products.map((p: Product) => {
          const enrolled = enrolledIds.has(p.id);
          const notForSale = Boolean(p.amount_minor) && !p.checkout_configured;
          return (
            <li key={p.id}>
              <Panel>
                <SectionLabel>{p.kind}</SectionLabel>
                <h2 className="mt-2 text-xl font-semibold tracking-[-0.02em] text-cream">{p.title}</h2>
                <p className="mt-2 text-sm text-mist">{p.description}</p>
                <p className="mt-4 text-sm font-semibold text-brand">
                  {p.amount_minor ? formatMoney(p.amount_minor, p.currency) : "Included"}
                </p>
                {notForSale ? (
                  <p className="mt-3 text-sm text-mist">Not for sale yet.</p>
                ) : (
                  <Button
                    className="mt-4"
                    type="button"
                    disabled={enrolled}
                    loading={busyId === p.id}
                    onClick={async () => {
                      setBusyId(p.id);
                      try {
                        const res = await api.enrol(p.id);
                        if (res.status === "checkout_required" && res.checkout_url) {
                          window.location.href = res.checkout_url;
                        } else {
                          toast.success("Enrolled.");
                          await load.reload();
                        }
                      } catch (err) {
                        toast.error(err instanceof Error ? err.message : "Could not enrol.");
                      } finally {
                        setBusyId(null);
                      }
                    }}
                  >
                    {enrolled ? "Enrolled" : "Enrol"}
                  </Button>
                )}
              </Panel>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
