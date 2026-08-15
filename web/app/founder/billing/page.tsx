"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { MetaList, MetaRow, Panel } from "@/components/ui/panel";
import { api } from "@/lib/api";
import { UNLOCK_PRICE } from "@/lib/domain/access";
import { useSession } from "@/stores/session";
import { toast } from "sonner";

function planLabel(status: string | undefined) {
  if (status === "active") return `${UNLOCK_PRICE.label} / month`;
  if (status === "past_due") return `${UNLOCK_PRICE.label} / month · past due`;
  if (status === "canceled") return "Canceled";
  return "Trial / unpaid";
}

function Inner() {
  const params = useSearchParams();
  const refresh = useSession((s) => s.refresh);
  const session = useSession((s) => s.session);
  const status = params.get("checkout");
  const [busy, setBusy] = useState(false);
  const subscribed =
    session?.subscriptionStatus === "active" || session?.subscriptionStatus === "past_due";

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
            {session?.hasAccess || subscribed ? "Unlocked" : "Locked"}
          </MetaRow>
          <MetaRow label="Plan">{planLabel(session?.subscriptionStatus)}</MetaRow>
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
        {subscribed ? (
          <Button
            type="button"
            onClick={async () => {
              setBusy(true);
              try {
                const portal = await api.billingPortal();
                window.location.href = portal.portal_url;
              } catch (err) {
                toast.error(err instanceof Error ? err.message : "Could not open billing.");
                setBusy(false);
              }
            }}
          >
            Manage billing
          </Button>
        ) : (
          <Button href="/founder/paywall">Subscribe</Button>
        )}
        <Button href="/founder" variant="ghost">
          Back to the desk
        </Button>
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
