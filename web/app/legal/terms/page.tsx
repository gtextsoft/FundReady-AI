import type { Metadata } from "next";
import { LandingShell } from "@/components/layout/landing-shell";

export const metadata: Metadata = {
  title: "Terms — FundReady",
  description: "Terms of use for the FundReady audit and brokerage platform.",
};

export default function TermsPage() {
  return (
    <LandingShell eyebrow="LEGAL" title="Terms of use">
      <p>Last updated 15 August 2026.</p>
      <p>
        FundReady provides an evidence-weighted investment-readiness audit and a SACI-brokered
        introduction between founders and investors. Use of the service is an agreement to these
        terms.
      </p>
      <h2 className="font-display text-xl text-cream">Not investment advice</h2>
      <p>
        Scores, verdicts, mentor replies, and analyst chat are decision support. They are not an
        offer, solicitation, or recommendation to buy or sell any security.
      </p>
      <h2 className="font-display text-xl text-cream">Brokerage</h2>
      <p>
        SACI stands between the two sides. An investor note is for SACI only — the founder never
        sees it. Expressing interest does not notify the founder. A meeting exists for the founder
        only after SACI confirms it. A full report reaches an investor only through a logged admin
        reveal.
      </p>
      <h2 className="font-display text-xl text-cream">Accounts</h2>
      <p>
        You must give accurate details, keep credentials private, and complete email verification
        before gated actions. Admins must enrol MFA. We may suspend an account that abuses the
        platform or attempts to route around the brokerage.
      </p>
      <h2 className="font-display text-xl text-cream">Payments</h2>
      <p>
        The founder desk is a monthly subscription after the trial. Catalogue items may require a
        separate Stripe Checkout. Fees are processed by Stripe; chargebacks follow Stripe&apos;s
        process.
      </p>
      <h2 className="font-display text-xl text-cream">Acceptable use</h2>
      <p>
        Do not upload malware, scrape other tenants&apos; data, or prompt the mentor or analyst to
        reveal another startup. Cross-tenant retrieval is refused by design.
      </p>
    </LandingShell>
  );
}
