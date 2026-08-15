"use client";

import { useState } from "react";
import { Sparkles, Zap } from "lucide-react";
import { UNLOCK_BENEFITS, UNLOCK_PRICE } from "@/lib/domain/access";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { toast } from "sonner";

export default function PaywallPage() {
  const [busy, setBusy] = useState(false);

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <PageHeader
        eyebrow="Unlock"
        title={`${UNLOCK_PRICE.label} / month.`}
        description="Monthly subscription. Cancel any time. Restores the desk after the 14-day trial."
      />
      <Panel className="bg-rail-promo">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white text-brand shadow-sm dark:bg-surface">
          <Sparkles size={16} strokeWidth={1.75} />
        </div>
        <ul className="mt-4 space-y-2.5 text-sm text-cream">
          {UNLOCK_BENEFITS.map((b) => (
            <li key={b} className="flex gap-2">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
              {b}
            </li>
          ))}
        </ul>
        <Button
          className="mt-6 w-full"
          type="button"
          loading={busy}
          onClick={async () => {
            setBusy(true);
            try {
              const session = await api.checkout();
              window.location.href = session.checkout_url;
            } catch (err) {
              toast.error(err instanceof Error ? err.message : "Could not start checkout.");
              setBusy(false);
            }
          }}
        >
          <Zap size={16} strokeWidth={2} />
          Continue to Stripe
        </Button>
        <Button href="/founder" variant="quiet" className="mt-2 w-full">
          Back to the desk
        </Button>
      </Panel>
    </div>
  );
}
