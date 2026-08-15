import Link from "next/link";
import { LandingFooter } from "@/components/layout/landing-footer";
import { LandingNav } from "@/components/layout/landing-nav";

const CHECKS = [
  "Market opportunity",
  "Product validation",
  "Commercial traction",
  "Unit economics",
  "Team & governance",
  "Legal & compliance",
  "Scalability & defensibility",
  "Raise & investor fit",
];

export default function LandingPage() {
  return (
    <div id="main" tabIndex={-1} className="relative min-h-dvh bg-bg text-cream">
      <LandingNav />

      <section className="relative mx-auto max-w-[1240px] overflow-hidden px-5 pb-24 pt-16 lg:min-h-[690px] lg:px-7 lg:pt-24">
        <p className="text-[11px] font-extrabold tracking-[0.2em] text-brass">
          <span className="mr-2.5 inline-block h-0.5 w-[22px] bg-brass align-middle" />
          AI-ASSISTED INVESTMENT READINESS
        </p>
        <h1 className="mt-6 max-w-3xl font-display text-[44px] leading-[0.98] tracking-[-0.04em] sm:text-6xl lg:text-[76px]">
          Know if your business
          <br />
          <em className="font-normal italic text-brass">is fund ready.</em>
        </h1>
        <p className="mt-6 max-w-[570px] text-lg leading-[1.65] text-mist">
          Fundready interrogates your business like an investor: testing claims against
          evidence, detecting red flags, and generating a country-aware plan to close the gaps.
        </p>
        <div className="mt-8 flex flex-col items-start gap-5 sm:flex-row sm:items-center">
          <Link
            href="/sign-up?role=founder"
            className="inline-flex items-center justify-between rounded-[4px] bg-brass px-[22px] py-[17px] text-sm font-bold text-white hover:bg-brass-hover"
          >
            Run my full audit <span className="ml-8">→</span>
          </Link>
          <span className="text-xs text-mist-2">Free · 15–20 minutes · Private</span>
        </div>
        <div className="mt-12 flex flex-wrap gap-8">
          {[
            ["70+", "investment checks"],
            ["8 dimensions", "full business diagnosis"],
            ["Explainable", "every score has a reason"],
          ].map(([k, v]) => (
            <div key={k} className="border-l-2 border-line-strong pl-3.5">
              <p className="font-display text-lg">{k}</p>
              <p className="mt-1 text-[11px] text-mist-2">{v}</p>
            </div>
          ))}
        </div>

        <div className="score-card-shadow relative mt-16 w-full max-w-[430px] border border-line bg-surface p-[26px] lg:absolute lg:right-7 lg:top-[85px] lg:mt-0 lg:rotate-1">
          <div className="pointer-events-none absolute inset-[18px_-18px_-18px_18px] -z-10 hidden border border-line-strong lg:block" />
          <div className="flex justify-between border-b border-line pb-4 text-[11px] tracking-[0.15em] text-mist">
            <span>FUNDREADY AI REPORT</span>
            <b className="tracking-normal text-brass">Evidence confidence 89%</b>
          </div>
          <div className="grid items-center gap-5 py-7 sm:grid-cols-[135px_1fr]">
            <div className="mx-auto flex h-[125px] w-[125px] flex-col items-center justify-center rounded-full border-[10px] border-lime border-l-line">
              <span className="font-display text-[45px] leading-none">78</span>
              <small className="text-mist">/ 100</small>
            </div>
            <div>
              <span className="rounded-sm bg-lime px-2.5 py-1.5 text-[11px] font-extrabold tracking-wider text-accent-ink">
                CONDITIONALLY READY
              </span>
              <h3 className="mt-4 font-display text-[23px]">Strong case. Three blockers.</h3>
              <p className="mt-1.5 text-xs leading-relaxed text-mist">
                Traction is credible. Financial controls and concentration risk need attention
                before diligence.
              </p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-5">
            {[
              ["Market", "88%"],
              ["Traction", "81%"],
              ["Finance", "61%"],
              ["Governance", "68%"],
            ].map(([name, w]) => (
              <div key={name} className="text-[11px] text-mist">
                {name}
                <span className="relative mt-1.5 block h-1 bg-surface-2">
                  <i className="absolute inset-y-0 left-0 bg-brass" style={{ width: w }} />
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="flex flex-wrap items-center justify-between gap-4 bg-brass px-5 py-6 text-white lg:px-[max(30px,calc(50vw-592px))]">
        <span className="hidden text-[9px] tracking-[0.15em] opacity-70 sm:block">
          AN INVESTOR-GRADE DIAGNOSTIC
        </span>
        {["Evidence", "Contradictions", "Risk", "Investor fit", "Action plan"].map((item) => (
          <b key={item} className="whitespace-nowrap font-display text-sm font-normal lg:text-[17px]">
            {item}
          </b>
        ))}
      </section>

      <section id="how" className="mx-auto max-w-[1184px] px-5 py-20 lg:px-7 lg:py-[110px]">
        <p className="text-[11px] font-extrabold tracking-[0.2em] text-brass">HOW FUNDREADY WORKS</p>
        <h2 className="mt-4 font-display text-[38px] leading-tight tracking-[-0.03em] lg:text-[55px]">
          More than a questionnaire.
        </h2>
        <p className="mt-3 max-w-2xl text-mist">
          A structured decision engine compares your claims, numbers and documentation against
          investor expectations.
        </p>
        <div className="mt-14 grid border-t border-line md:grid-cols-3">
          {[
            {
              n: "01",
              t: "Deep founder interview",
              d: "Eight focused modules cover the company, market, product, traction, economics, team, compliance and raise.",
            },
            {
              n: "02",
              t: "Evidence-weighted analysis",
              d: "Assertions earn less than verified data. Contradictions, missing controls and concentration risks reduce confidence.",
            },
            {
              n: "03",
              t: "Investment action report",
              d: "Receive dimension scores, critical blockers, investor fit, diligence readiness and a practical 90-day plan.",
            },
          ].map((step, i) => (
            <article
              key={step.n}
              className={`py-8 pr-8 md:py-9 ${i < 2 ? "md:border-r md:border-line md:mr-8" : ""}`}
            >
              <span className="text-[11px] text-brass">{step.n}</span>
              <h3 className="mt-3 font-display text-[25px]">{step.t}</h3>
              <p className="mt-3 text-sm leading-relaxed text-mist">{step.d}</p>
            </article>
          ))}
        </div>
      </section>

      <section
        id="checks"
        className="grid gap-10 bg-navy px-5 py-20 text-white lg:grid-cols-[0.8fr_1.2fr] lg:gap-[85px] lg:px-[max(28px,calc(50vw-592px))] lg:py-[105px]"
      >
        <div>
          <p className="text-[11px] font-extrabold tracking-[0.2em] text-lime">THE FRAMEWORK</p>
          <h2 className="mt-4 font-display text-[38px] leading-tight tracking-[-0.03em] lg:text-5xl">
            Audited from every
            <br />
            <em className="font-normal italic text-lime">investor angle.</em>
          </h2>
          <p className="mt-6 max-w-sm text-sm leading-relaxed text-white/70">
            Investors browse summary cards. Full reports open only when SACI brokers the meeting.
          </p>
          <Link
            href="/sign-up?role=investor"
            className="mt-8 inline-flex border border-white/20 px-5 py-3 text-sm text-white hover:border-lime hover:text-lime"
          >
            Enter dealflow
          </Link>
        </div>
        <div className="grid sm:grid-cols-2">
          {CHECKS.map((title, i) => (
            <article key={title} className="border-b border-l border-white/15 p-7">
              <span className="text-[10px] text-lime">{String(i + 1).padStart(2, "0")}</span>
              <h3 className="mt-2 font-display text-xl">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-white/70">
                Claims, supporting evidence, risks and readiness are assessed together.
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className="bg-lime px-5 py-[110px] text-center text-navy">
        <span className="text-[10px] font-extrabold tracking-[0.2em]">DON’T PITCH BLIND</span>
        <h2 className="mt-4 font-display text-[38px] leading-tight tracking-[-0.03em] lg:text-[55px]">
          Find the gaps before
          <br />
          investors do.
        </h2>
        <Link
          href="/sign-up?role=founder"
          className="mt-6 inline-flex items-center rounded-[4px] bg-navy px-[22px] py-[17px] text-sm font-bold text-white hover:opacity-90"
        >
          Start the Fundready audit <b className="ml-2">→</b>
        </Link>
      </section>

      <LandingFooter />
    </div>
  );
}
