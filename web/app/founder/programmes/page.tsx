"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LockedCard } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Panel, SectionLabel } from "@/components/ui/panel";
import { api, type Product } from "@/lib/api";
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
      const p = await api.listProducts();
      return p.items.filter((x) => x.active);
    },
    [],
    (d) => d.length === 0,
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

  return (
    <div className="space-y-6">
      <PageHeader title="Programmes" description="Matched to gaps when the audit names them. Enrolment is optional." />
      <ul className="grid gap-4 md:grid-cols-2">
        {load.data.map((p: Product) => (
          <li key={p.id}>
            <Panel>
              <SectionLabel>{p.kind}</SectionLabel>
              <h2 className="mt-2 text-xl font-semibold tracking-[-0.02em] text-cream">{p.title}</h2>
              <p className="mt-2 text-sm text-mist">{p.description}</p>
              <p className="mt-4 text-sm font-semibold text-brand">
                {p.amount_minor ? formatMoney(p.amount_minor, p.currency) : "Included"}
              </p>
              <Button
                className="mt-4"
                type="button"
                loading={busyId === p.id}
                onClick={async () => {
                  setBusyId(p.id);
                  try {
                    const res = await api.enrol(p.id);
                    if (res.status === "checkout_required" && res.checkout_url) {
                      window.location.href = res.checkout_url;
                    } else {
                      toast.success("Enrolled.");
                    }
                  } catch (err) {
                    toast.error(err instanceof Error ? err.message : "Could not enrol.");
                  } finally {
                    setBusyId(null);
                  }
                }}
              >
                Enrol
              </Button>
            </Panel>
          </li>
        ))}
      </ul>
    </div>
  );
}
