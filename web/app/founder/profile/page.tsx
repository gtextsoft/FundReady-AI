"use client";

import Link from "next/link";
import { useState } from "react";
import { daysLeftInTrial, hasAccess } from "@/lib/domain/access";
import { founderAccount } from "@/lib/format";
import { useSession } from "@/stores/session";
import { MfaEnrolForm } from "@/components/auth/mfa-enrol-form";
import { PageHeader } from "@/components/ui/page-header";
import { MetaList, MetaRow, Panel } from "@/components/ui/panel";

export default function FounderProfilePage() {
  const session = useSession((s) => s.session);
  const refresh = useSession((s) => s.refresh);
  const [enrolledHere, setEnrolledHere] = useState(false);
  const account = founderAccount(session);
  const days = session ? daysLeftInTrial(account) : 0;
  const unlocked = session ? hasAccess(account) : false;

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
          <MetaRow label="Access">
            {unlocked
              ? session?.subscriptionStatus === "active"
                ? "Unlocked"
                : `${days} days of trial left`
              : "Trial ended"}
          </MetaRow>
          <MetaRow label="MFA">{session?.mfaEnabled ? "Enrolled" : "Off"}</MetaRow>
        </MetaList>
      </Panel>
      <div className="flex flex-wrap gap-4 text-sm">
        <Link href="/founder/billing" className="font-semibold text-brand hover:text-brand-hover">
          Billing →
        </Link>
        {!unlocked ? (
          <Link href="/founder/paywall" className="font-semibold text-brand hover:text-brand-hover">
            Unlock access →
          </Link>
        ) : null}
        {!session?.emailVerified ? (
          <Link href="/verify-email" className="font-semibold text-brand hover:text-brand-hover">
            Confirm email →
          </Link>
        ) : null}
      </div>
      {session?.mfaEnabled && !enrolledHere ? null : (
        <Panel>
          <p className="text-lg font-semibold tracking-[-0.02em] text-cream">Two-factor</p>
          <p className="mt-1 text-sm text-mist">Optional for founders. Required for every admin action.</p>
          <MfaEnrolForm
            onEnrolled={async () => {
              setEnrolledHere(true);
              await refresh();
            }}
          />
        </Panel>
      )}
    </div>
  );
}
