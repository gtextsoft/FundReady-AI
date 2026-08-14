"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { MetaList, MetaRow, Panel } from "@/components/ui/panel";
import { useSession } from "@/stores/session";

function Inner() {
  const params = useSearchParams();
  const refresh = useSession((s) => s.refresh);
  const session = useSession((s) => s.session);
  const status = params.get("checkout");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <PageHeader
        title={status === "success" ? "Payment received." : status === "cancel" ? "Checkout cancelled." : "Billing"}
        description="Entitlement arrives from Stripe, not from this page. If you just paid, refresh once."
      />
      <Panel>
        <MetaList>
          <MetaRow label="Access">
            {session?.hasAccess || session?.subscriptionStatus === "active" ? "Unlocked" : "Locked"}
          </MetaRow>
          <MetaRow label="Plan">
            {session?.subscriptionStatus === "active" ? "One-time unlock" : "Trial / unpaid"}
          </MetaRow>
        </MetaList>
      </Panel>
      <div className="flex flex-wrap gap-3">
        <Button
          type="button"
          variant="ghost"
          loading={busy}
          onClick={async () => {
            setBusy(true);
            await refresh();
            setBusy(false);
          }}
        >
          Refresh entitlement
        </Button>
        <Button href="/founder">Back to the desk</Button>
      </div>
    </div>
  );
}

export default function BillingPage() {
  return (
    <Suspense>
      <Inner />
    </Suspense>
  );
}
