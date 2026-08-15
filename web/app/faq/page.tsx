import type { Metadata } from "next";
import { LandingShell } from "@/components/layout/landing-shell";

export const metadata: Metadata = {
  title: "FAQ — FundReady",
  description: "What investors see, how SACI brokers meetings, and how the trial works.",
};

const ITEMS = [
  {
    q: "What does an investor see?",
    a: "A summary card only: sector, stage, country, and the two verdicts. Not your figures, findings, or contact details. The full report opens only when a SACI admin reveals it.",
  },
  {
    q: "Who books the meeting?",
    a: "SACI hosts every introduction. An investor may propose a slot after interest is approved. A founder sees the meeting only once SACI confirms it.",
  },
  {
    q: "Is the company badge a registry check?",
    a: "No. You upload a registration certificate and SACI reviews it. There is no live registry API. Rejected verification blocks mentor and visibility; an unsubmitted badge does not.",
  },
  {
    q: "What happens after the trial?",
    a: "Fourteen days, then $79 a month. Cancel any time from billing. The desk stays yours while the subscription is active or Stripe is retrying a failed card.",
  },
  {
    q: "Is this investment advice?",
    a: "No. FundReady is decision support: an evidence-weighted audit and a brokered introduction. It does not recommend securities or tell anyone to invest.",
  },
];

export default function FaqPage() {
  return (
    <LandingShell eyebrow="FAQ" title="Straight answers.">
      {ITEMS.map((item) => (
        <section key={item.q}>
          <h2 className="font-display text-xl text-cream">{item.q}</h2>
          <p className="mt-2">{item.a}</p>
        </section>
      ))}
    </LandingShell>
  );
}
