"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Field, Select, TextArea } from "@/components/ui/field";
import { BrandMark } from "@/components/brand/mark";
import { PageSkeleton } from "@/components/ui/skeleton";
import { COUNTRY_OPTIONS, SECTORS, STAGES } from "@/lib/domain/email";
import {
  AUDIT_READY_TOTAL,
  EMPTY_FORM,
  FIELD_LABELS,
  ONBOARDING_STEPS,
  STEP_REQUIRED,
  auditReadyCount,
  firstIncompleteStep,
  fromWire,
  isAuditReady,
  toWire,
  type FounderForm,
} from "@/lib/domain/profile";
import { api } from "@/lib/api";
import { ApiFailure } from "@/lib/api/errors";
import { cn } from "@/lib/utils";
import { useSession } from "@/stores/session";

function YesNo({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <Select label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Select</option>
      <option>Yes</option>
      <option>No</option>
    </Select>
  );
}

function founderNeedsOnboardingFromSaved(saved: { missing_fields?: string[] }) {
  return (saved.missing_fields?.length ?? 0) > 0;
}

export default function OnboardingPage() {
  const router = useRouter();
  const signOut = useSession((s) => s.signOut);
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<FounderForm>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<Partial<Record<keyof FounderForm, string>>>({});
  const [busy, setBusy] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    let stop = false;
    void (async () => {
      try {
        const existing = await api.getProfile();
        if (stop) return;
        const next = fromWire(existing);
        setForm(next);
        setStep(firstIncompleteStep(next));
      } catch (err) {
        if (!(err instanceof ApiFailure && err.code === "not_found") && !stop) {
          setError(err instanceof ApiFailure ? err.message : "Could not load the profile.");
        }
      } finally {
        if (!stop) setHydrated(true);
      }
    })();
    return () => {
      stop = true;
    };
  }, []);

  function set<K extends keyof FounderForm>(key: K, value: FounderForm[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setFieldError((e) => ({ ...e, [key]: undefined }));
  }

  function validateStep() {
    const keys = STEP_REQUIRED[step] ?? [];
    const next: Partial<Record<keyof FounderForm, string>> = {};
    for (const key of keys) {
      if (!String(form[key] ?? "").trim()) {
        next[key] = `${FIELD_LABELS[key] ?? key} is required.`;
      }
    }
    setFieldError(next);
    return Object.keys(next).length === 0;
  }

  async function persist() {
    const wire = toWire(form);
    try {
      const existing = await api.getProfile();
      return await api.updateProfile(existing.id, wire);
    } catch (err) {
      if (err instanceof ApiFailure && err.code === "not_found") {
        return await api.createProfile(wire);
      }
      throw err;
    }
  }

  async function saveAndContinue() {
    if (!validateStep()) {
      setError("Fill the required fields on this step.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const saved = await persist();
      if (step < ONBOARDING_STEPS.length - 1) {
        setStep(step + 1);
        return;
      }
      if (founderNeedsOnboardingFromSaved(saved) || !isAuditReady(form)) {
        setError(
          "The audit still needs the company, sector, country, description, how it makes money, stage, monthly revenue, monthly costs, cash, and team size.",
        );
        return;
      }
      router.push("/assessment");
    } catch (err) {
      setError(err instanceof ApiFailure ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  async function saveProgress() {
    setBusy(true);
    setError(null);
    try {
      await persist();
    } catch (err) {
      setError(err instanceof ApiFailure ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSignOut() {
    await signOut();
    router.replace("/sign-in");
  }

  const ready = auditReadyCount(form);
  const last = step === ONBOARDING_STEPS.length - 1;

  if (!hydrated) {
    return (
      <div id="main" tabIndex={-1} className="min-h-dvh bg-bg px-6 py-10">
        <div className="mx-auto max-w-2xl">
          <BrandMark />
          <div className="mt-10">
            <PageSkeleton rows={6} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div id="main" tabIndex={-1} className="min-h-dvh bg-bg px-6 py-10">
      <div className="mx-auto max-w-2xl">
        <div className="flex items-center justify-between gap-4">
          <BrandMark />
          <div className="flex gap-2">
            <Button type="button" variant="quiet" size="sm" loading={busy} onClick={() => void saveProgress()}>
              Save progress
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => void handleSignOut()}>
              Sign out
            </Button>
          </div>
        </div>
        <ol className="mt-8 flex gap-2" aria-label="Progress">
          {ONBOARDING_STEPS.map((name, i) => (
            <li key={name} className="flex-1">
              <span
                className={cn("block h-1.5 rounded-full", i <= step ? "bg-brass" : "bg-line")}
                aria-current={i === step ? "step" : undefined}
              />
              <span className="mt-2 hidden text-[11px] text-mist sm:block">{name}</span>
            </li>
          ))}
        </ol>
        <p className="mt-8 text-[11px] font-extrabold tracking-[0.18em] text-brass">
          STEP {step + 1} OF {ONBOARDING_STEPS.length} · {ONBOARDING_STEPS[step].toUpperCase()}
        </p>
        <p className="mt-2 text-sm text-mist">
          Audit-ready: {ready} / {AUDIT_READY_TOTAL}
        </p>
        <h1 className="mt-3 font-display text-4xl text-cream">Tell us about the company.</h1>
        <div className="mt-8 space-y-3 border border-line bg-surface p-8 shadow-[0_18px_50px_rgb(39_58_48_/_0.13)] md:p-12">
          {step === 0 ? (
            <>
              <Field label="Company name" value={form.company} error={fieldError.company} onChange={(e) => set("company", e.target.value)} />
              <Select label="Sector" value={form.sector} error={fieldError.sector} onChange={(e) => set("sector", e.target.value)}>
                <option value="">Select</option>
                {SECTORS.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </Select>
              <Select label="Country" value={form.location} error={fieldError.location} onChange={(e) => set("location", e.target.value)}>
                <option value="">Select</option>
                {COUNTRY_OPTIONS.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </Select>
              <Field label="Year founded" value={form.year} onChange={(e) => set("year", e.target.value)} />
              <TextArea label="What the business does" value={form.description} error={fieldError.description} onChange={(e) => set("description", e.target.value)} />
              <TextArea label="How it makes money" value={form.businessModel} error={fieldError.businessModel} onChange={(e) => set("businessModel", e.target.value)} />
              <Field label="Website" value={form.website} onChange={(e) => set("website", e.target.value)} />
            </>
          ) : null}
          {step === 1 ? (
            <>
              <Field label="Registered legal name" hint="Exactly as on the certificate." value={form.legalName} onChange={(e) => set("legalName", e.target.value)} />
              <Field label="Registered with" hint="CAC, CIPC, Companies House, …" value={form.registrar} onChange={(e) => set("registrar", e.target.value)} />
              <Field label="Registration number" value={form.registrationNumber} onChange={(e) => set("registrationNumber", e.target.value)} />
              <Field label="Year incorporated" value={form.incorporationYear} onChange={(e) => set("incorporationYear", e.target.value)} />
              <TextArea label="Licences or permissions" hint="What the model needs, and whether you hold them." value={form.licences} onChange={(e) => set("licences", e.target.value)} />
              <YesNo label="Traded before incorporation" value={form.tradedBeforeIncorporation} onChange={(v) => set("tradedBeforeIncorporation", v)} />
            </>
          ) : null}
          {step === 2 ? (
            <>
              <Select label="Stage" value={form.stage} error={fieldError.stage} onChange={(e) => set("stage", e.target.value)}>
                <option value="">Select</option>
                {STAGES.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </Select>
              <Field label="Monthly revenue" hint="Most recent full month, local currency, whole numbers. Use 0 if none." value={form.revenue} error={fieldError.revenue} onChange={(e) => set("revenue", e.target.value)} />
              <Field label="Monthly costs" hint="Operating costs that same month." value={form.costs} error={fieldError.costs} onChange={(e) => set("costs", e.target.value)} />
              <Field label="Cash on hand" value={form.cash} error={fieldError.cash} onChange={(e) => set("cash", e.target.value)} />
              <Field label="Cost of revenue" hint="Direct cost of delivering that revenue." value={form.costOfRevenue} onChange={(e) => set("costOfRevenue", e.target.value)} />
              <Field label="Revenue, last 12 months" value={form.revenue12m} onChange={(e) => set("revenue12m", e.target.value)} />
              <Field label="Revenue three months ago" value={form.revenue3mAgo} onChange={(e) => set("revenue3mAgo", e.target.value)} />
              <Field label="Costs three months ago" value={form.costs3mAgo} onChange={(e) => set("costs3mAgo", e.target.value)} />
              <Field label="Monthly marketing spend" value={form.marketingSpend} onChange={(e) => set("marketingSpend", e.target.value)} />
              <Field label="Total raised" value={form.totalRaised} onChange={(e) => set("totalRaised", e.target.value)} />
              <Field label="Raise target" value={form.raiseTarget} onChange={(e) => set("raiseTarget", e.target.value)} />
              <Field label="Founder salary / month" value={form.founderSalary} onChange={(e) => set("founderSalary", e.target.value)} />
              <TextArea label="Capital mix" hint="How much of what you have raised is grant, equity, or debt." value={form.capitalMix} onChange={(e) => set("capitalMix", e.target.value)} />
            </>
          ) : null}
          {step === 3 ? (
            <>
              <Field label="Paying customers" value={form.customers} onChange={(e) => set("customers", e.target.value)} />
              <Field label="Monthly active users" value={form.mau} onChange={(e) => set("mau", e.target.value)} />
              <Field label="ARPU / month" hint="Average revenue per customer." value={form.arpu} onChange={(e) => set("arpu", e.target.value)} />
              <Field label="Monthly churn %" hint="0–100. 2 means 2%." value={form.churn} onChange={(e) => set("churn", e.target.value)} />
              <Field label="CAC" hint="Cost to win one customer." value={form.cac} onChange={(e) => set("cac", e.target.value)} />
              <Field label="Pilots or LOIs, not yet paying" value={form.pilots} onChange={(e) => set("pilots", e.target.value)} />
              <Field label="Largest customer, % of revenue" hint="0–100." value={form.largestCustomerShare} onChange={(e) => set("largestCustomerShare", e.target.value)} />
            </>
          ) : null}
          {step === 4 ? (
            <>
              <TextArea
                label="Reachable market, and how you sized it"
                placeholder="12,000 registered pharmacies in Lagos × ₦5,000/month = ₦60m/month. We cannot serve other states yet."
                value={form.marketSize}
                error={fieldError.marketSize}
                onChange={(e) => set("marketSize", e.target.value)}
              />
              <TextArea label="Who else solves this today" value={form.competition} onChange={(e) => set("competition", e.target.value)} />
              <TextArea label="The constraint on growth right now" value={form.growthConstraint} onChange={(e) => set("growthConstraint", e.target.value)} />
              <TextArea label="What new capital buys" value={form.useOfFunds} onChange={(e) => set("useOfFunds", e.target.value)} />
              <Select label="Cost to serve one more customer" value={form.deliveryCostTrend} onChange={(e) => set("deliveryCostTrend", e.target.value)}>
                <option value="">Select</option>
                <option>Gone down</option>
                <option>Stayed flat</option>
                <option>Gone up</option>
                <option>Not sure yet</option>
              </Select>
            </>
          ) : null}
          {step === 5 ? (
            <>
              <Field label="Founders" value={form.founders} error={fieldError.founders} onChange={(e) => set("founders", e.target.value)} />
              <Field label="Founders full-time" value={form.foundersFullTime} onChange={(e) => set("foundersFullTime", e.target.value)} />
              <Field label="Team size" hint="Everyone working on this, including founders." value={form.teamSize} error={fieldError.teamSize} onChange={(e) => set("teamSize", e.target.value)} />
              <TextArea label="Founder experience" value={form.founderExperience} onChange={(e) => set("founderExperience", e.target.value)} />
              <TextArea
                label="What breaks if one person leaves"
                hint="A sentence, not yes/no."
                value={form.keyPerson}
                onChange={(e) => set("keyPerson", e.target.value)}
              />
              <TextArea label="Roles still needed" value={form.hiringGaps} onChange={(e) => set("hiringGaps", e.target.value)} />
            </>
          ) : null}
          {step === 6 ? (
            <>
              <YesNo label="Company owns the IP" value={form.ipOwned} onChange={(v) => set("ipOwned", v)} />
              <YesNo label="Contracts survive a change of owner" value={form.contractsTransferable} onChange={(v) => set("contractsTransferable", v)} />
              <TextArea label="Cap table, in summary" value={form.capTable} onChange={(e) => set("capTable", e.target.value)} />
              <YesNo label="Someone else could run day-to-day from written process" value={form.operationsDocumented} onChange={(v) => set("operationsDocumented", v)} />
              <YesNo label="Bank accounts, domains, and subscriptions are in the company name" value={form.systemsInCompanyName} onChange={(v) => set("systemsInCompanyName", v)} />
              <TextArea label="Suppliers or platforms that would hurt most to lose" value={form.supplierDependencies} onChange={(e) => set("supplierDependencies", e.target.value)} />
              <TextArea label="Does revenue depend on one channel, platform, or partner?" value={form.channelDependency} onChange={(e) => set("channelDependency", e.target.value)} />
              <Field label="Recurring or contracted revenue %" hint="0–100." value={form.recurringRevenue} onChange={(e) => set("recurringRevenue", e.target.value)} />
              <Field label="Typical contract length, months" value={form.typicalContractMonths} onChange={(e) => set("typicalContractMonths", e.target.value)} />
              <TextArea label="Major contracts, loans, or obligations" value={form.materialContracts} onChange={(e) => set("materialContracts", e.target.value)} />
              <TextArea label="Tax filings" hint="VAT, CIT, PAYE, or equivalent — current or not." value={form.taxFiling} onChange={(e) => set("taxFiling", e.target.value)} />
              <TextArea label="FX exposure" hint="Invoice currency versus the currency costs are paid in." value={form.fxExposure} onChange={(e) => set("fxExposure", e.target.value)} />
              <TextArea label="Local-content or ownership rules" hint="BEE, local participation, foreign-ownership caps that would affect a sale." value={form.localContent} onChange={(e) => set("localContent", e.target.value)} />
            </>
          ) : null}
          {error ? <p className="mt-4 text-sm text-fail">{error}</p> : null}
          <div className="mt-8 flex justify-between">
            <Button variant="ghost" type="button" disabled={step === 0} onClick={() => setStep(step - 1)}>
              Back
            </Button>
            <Button type="button" loading={busy} onClick={() => void saveAndContinue()}>
              {last ? "Run AI assessment" : "Continue"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
