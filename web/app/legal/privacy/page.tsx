import type { Metadata } from "next";
import { LandingShell } from "@/components/layout/landing-shell";

export const metadata: Metadata = {
  title: "Privacy — FundReady",
  description: "How FundReady handles founder, investor, and brokerage data.",
};

export default function PrivacyPage() {
  return (
    <LandingShell eyebrow="LEGAL" title="Privacy">
      <p>Last updated 15 August 2026.</p>
      <p>
        We collect the account details you register with, the company profile and documents you
        upload, audit outputs we generate, and the interest and meeting records SACI needs to
        broker an introduction.
      </p>
      <h2 className="font-display text-xl text-cream">What investors do not see</h2>
      <p>
        Discovery cards are summary-tier only. Submitted figures, findings, and founder contact
        stay off the card. Investor notes to SACI are never shown to the founder.
      </p>
      <h2 className="font-display text-xl text-cream">Processors</h2>
      <p>
        We use Stripe for payments, an object store for documents, email delivery for
        transactional messages, and a model provider for audits, mentor, and analyst chat.
        Prompts are fenced; another startup&apos;s data is not retrieved even if a message asks
        for it.
      </p>
      <h2 className="font-display text-xl text-cream">Retention</h2>
      <p>
        Account and audit records stay while the account is active. You can ask us to export or
        erase personal data; some brokerage and audit-log rows are kept where the law or the
        integrity of a reveal requires it.
      </p>
      <p className="text-mist-2">Decision support, not investment advice.</p>
    </LandingShell>
  );
}
