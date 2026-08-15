import type { Metadata } from "next";
import Link from "next/link";
import { LandingShell } from "@/components/layout/landing-shell";
import { TRIAL_DAYS, UNLOCK_PRICE } from "@/lib/domain/access";

export const metadata: Metadata = {
  title: "Pricing — FundReady",
  description: "14-day founder trial, then $79 a month. Investors are thesis-gated, not paid.",
};

export default function PricingPage() {
  return (
    <LandingShell eyebrow="PRICING" title="One audit desk. Monthly.">
      <p>
        Founders get a {TRIAL_DAYS}-day trial with the full desk: intake, audit, readiness tasks,
        mentor, and publish. After that, {UNLOCK_PRICE.label} a month keeps access. Cancel any time
        from billing.
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        <section className="border border-line bg-surface p-6">
          <p className="text-[11px] font-extrabold tracking-[0.16em] text-brass">FOUNDERS</p>
          <h2 className="mt-3 font-display text-2xl text-cream">{UNLOCK_PRICE.label} / month</h2>
          <p className="mt-2">
            {TRIAL_DAYS} days free, then the subscription. Includes dealflow listing when you
            publish, the AI mentor, and catalogue programmes sold separately.
          </p>
          <Link
            href="/sign-up?role=founder"
            className="mt-6 inline-flex rounded-[4px] bg-brass px-5 py-3 text-sm font-bold text-white hover:bg-brass-hover"
          >
            Start the trial
          </Link>
        </section>
        <section className="border border-line bg-surface p-6">
          <p className="text-[11px] font-extrabold tracking-[0.16em] text-brass">INVESTORS</p>
          <h2 className="mt-3 font-display text-2xl text-cream">Thesis review, not a fee</h2>
          <p className="mt-2">
            Investor access is gated by an accepted thesis, not a card. You see summary cards.
            SACI brokers the meeting and any report reveal.
          </p>
          <Link
            href="/sign-up?role=investor"
            className="mt-6 inline-flex border border-line px-5 py-3 text-sm text-cream hover:border-brass"
          >
            Enter dealflow
          </Link>
        </section>
      </div>
      <p>
        Programmes, mentorship, and events are a separate catalogue. A priced item enrols through
        Stripe Checkout once SACI attaches a Price. Already on a plan?{" "}
        <Link href="/founder/billing" className="text-brass hover:text-cream">
          Open billing
        </Link>
        .
      </p>
      <p className="text-mist-2">Decision support, not investment advice.</p>
    </LandingShell>
  );
}
