"use client";

import { useState } from "react";
import { Building2, Linkedin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Field, Select, TextArea } from "@/components/ui/field";
import { Badge, ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { MetaList, MetaRow, Panel, SectionLabel } from "@/components/ui/panel";
import { COUNTRY_TO_CODE, SECTORS, STAGES, STAGE_TO_WIRE } from "@/lib/domain/email";
import { api, type InvestorProfile } from "@/lib/api";
import { humanize } from "@/lib/format";
import { useLoad } from "@/lib/hooks/use-load";
import { toast } from "sonner";

const CODE_TO_COUNTRY = Object.fromEntries(
  Object.entries(COUNTRY_TO_CODE).map(([name, row]) => [row.code, name]),
);
const WIRE_TO_STAGE = Object.fromEntries(Object.entries(STAGE_TO_WIRE).map(([label, wire]) => [wire, label]));

function stageLabel(value: string | undefined) {
  if (!value) return "—";
  return WIRE_TO_STAGE[value] ?? humanize(value);
}

function ThesisReadout({ profile }: { profile: Partial<InvestorProfile> }) {
  return (
    <MetaList>
      <MetaRow label="Firm">{profile.firm || "—"}</MetaRow>
      <MetaRow label="Investor type">{profile.investor_type || "—"}</MetaRow>
      <MetaRow label="Country">{CODE_TO_COUNTRY[profile.country ?? ""] ?? profile.country ?? "—"}</MetaRow>
      <MetaRow label="LinkedIn">{profile.linkedin_url || "—"}</MetaRow>
      <MetaRow label="Primary sector">{profile.thesis_sectors?.[0] || "—"}</MetaRow>
      <MetaRow label="Stage">{stageLabel(profile.thesis_stages?.[0])}</MetaRow>
      <MetaRow label="Risk notes">{profile.risk_notes || "—"}</MetaRow>
    </MetaList>
  );
}

export default function InvestorVerifyPage() {
  const [profile, setProfile] = useState<Partial<InvestorProfile>>({});
  const [saving, setSaving] = useState(false);
  const load = useLoad(async () => {
    const p = await api.getInvestorMe();
    setProfile(p);
    return p;
  }, []);

  if (load.status === "loading") return <PageSkeleton />;
  if (load.status === "error") return <ErrorState message={load.message} onRetry={() => void load.reload()} />;

  const status = profile.review_status ?? "none";
  const locked = status === "in_review" || status === "accepted";
  const thesisReady = Boolean(profile.firm && profile.investor_type && profile.country);

  async function submitThesis() {
    setSaving(true);
    try {
      const saved = await api.putInvestorMe({
        firm: profile.firm,
        investor_type: profile.investor_type,
        country: profile.country,
        linkedin_url: profile.linkedin_url,
        thesis_sectors: profile.thesis_sectors ?? [],
        thesis_stages: profile.thesis_stages ?? [],
        thesis_geographies: profile.thesis_geographies ?? [],
        ticket_min_minor: profile.ticket_min_minor,
        ticket_max_minor: profile.ticket_max_minor,
        ticket_currency: profile.ticket_currency,
        risk_notes: profile.risk_notes,
      });
      setProfile(saved);
      toast.success("Thesis submitted for review.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not submit.");
    } finally {
      setSaving(false);
    }
  }

  if (locked) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <PageHeader
          eyebrow="Investor desk"
          title="Profile"
          description={
            status === "accepted"
              ? "SACI accepted this thesis. It is locked."
              : "Submitted. SACI will accept or reject this thesis."
          }
        />
        <Panel className="space-y-4">
          <Badge tone={status === "accepted" ? "pass" : "hold"}>
            {status === "accepted" ? "Accepted" : "In review"}
          </Badge>
          <ThesisReadout profile={profile} />
        </Panel>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        eyebrow="Investor desk"
        title="Thesis"
        description="Tell SACI who you are and what you look for. Submitting sends it for review. The founder never sees this form."
      />

      {status === "rejected" ? (
        <Panel className="space-y-2">
          <Badge tone="fail">Rejected</Badge>
          <p className="text-sm text-mist">Update the thesis and submit again for SACI to review.</p>
        </Panel>
      ) : null}

      <Panel className="space-y-7">
        <div>
          <SectionLabel>Profile</SectionLabel>
          <p className="mt-1 text-sm text-mist">How you appear on the desk.</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field
              label="Firm"
              value={profile.firm ?? ""}
              onChange={(e) => setProfile((p) => ({ ...p, firm: e.target.value }))}
            />
            <Select
              label="Investor type"
              value={profile.investor_type ?? ""}
              onChange={(e) => setProfile((p) => ({ ...p, investor_type: e.target.value }))}
            >
              <option value="">Select</option>
              <option>Angel investor</option>
              <option>Venture capital</option>
              <option>Private equity</option>
              <option>Family office</option>
              <option>Corporate / strategic</option>
            </Select>
            <Select
              label="Country"
              value={profile.country ?? ""}
              onChange={(e) => setProfile((p) => ({ ...p, country: e.target.value }))}
            >
              <option value="">Select</option>
              <option value="NG">Nigeria</option>
              <option value="GH">Ghana</option>
              <option value="KE">Kenya</option>
              <option value="ZA">South Africa</option>
              <option value="GB">United Kingdom</option>
              <option value="US">United States</option>
              <option value="AE">United Arab Emirates</option>
            </Select>
            <Field
              label="LinkedIn"
              placeholder="https://linkedin.com/in/…"
              value={profile.linkedin_url ?? ""}
              onChange={(e) => setProfile((p) => ({ ...p, linkedin_url: e.target.value }))}
            />
          </div>
        </div>

        <div className="h-px bg-black/5 dark:bg-white/10" />

        <div>
          <SectionLabel>Mandate</SectionLabel>
          <p className="mt-1 text-sm text-mist">What you actually look at. Used to match published companies.</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Select
              label="Primary sector"
              value={profile.thesis_sectors?.[0] ?? ""}
              onChange={(e) => setProfile((p) => ({ ...p, thesis_sectors: [e.target.value] }))}
            >
              <option value="">Select</option>
              {SECTORS.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </Select>
            <Select
              label="Stage"
              value={profile.thesis_stages?.[0] ?? ""}
              onChange={(e) => setProfile((p) => ({ ...p, thesis_stages: [e.target.value] }))}
            >
              <option value="">Select</option>
              {STAGES.map((s) => (
                <option key={s} value={STAGE_TO_WIRE[s]}>
                  {s}
                </option>
              ))}
            </Select>
            <TextArea
              label="Risk notes"
              className="sm:col-span-2"
              value={profile.risk_notes ?? ""}
              onChange={(e) => setProfile((p) => ({ ...p, risk_notes: e.target.value }))}
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-black/5 pt-5 dark:border-white/10">
          <p className="text-sm text-mist">
            {thesisReady
              ? "SACI reviews this before it is locked on your profile."
              : "Firm, type, and country are required to submit."}
          </p>
          <Button type="button" disabled={!thesisReady} loading={saving} onClick={() => void submitThesis()}>
            Submit
          </Button>
        </div>
      </Panel>

      <div className="flex flex-wrap gap-4 text-[12px] text-mist">
        <span className="inline-flex items-center gap-1.5">
          <Building2 size={14} strokeWidth={1.75} /> Firm stays with SACI
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Linkedin size={14} strokeWidth={1.75} /> LinkedIn is optional
        </span>
      </div>
    </div>
  );
}
