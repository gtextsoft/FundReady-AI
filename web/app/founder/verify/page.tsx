"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/field";
import { FileField } from "@/components/ui/file-field";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Panel } from "@/components/ui/panel";
import { api, putFile } from "@/lib/api";
import { COUNTRY_OPTIONS, COUNTRY_TO_CODE } from "@/lib/domain/email";
import { humanize } from "@/lib/format";
import { useStartup } from "@/lib/hooks/use-startup";
import { toast } from "sonner";

const STATUS: Record<string, string> = {
  none: "Not submitted",
  submitted: "Submitted",
  in_review: "In review",
  accepted: "Accepted",
  rejected: "Rejected",
};

export default function VerifyPage() {
  const { profile, loading, error, reload } = useStartup();
  const [legalName, setLegalName] = useState("");
  const [number, setNumber] = useState("");
  const [registrar, setRegistrar] = useState("");
  const [country, setCountry] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    const f = profile?.fields ?? {};
    setLegalName(String(f.legal_name?.value ?? ""));
    setNumber(String(f.registration_number?.value ?? ""));
    setRegistrar(String(f.registrar?.value ?? ""));
    if (profile?.country) {
      const match = COUNTRY_OPTIONS.find((c) => COUNTRY_TO_CODE[c]?.code === profile.country);
      if (match) setCountry(match);
    }
  }, [profile]);

  if (loading) return <PageSkeleton />;
  if (error) return <ErrorState message={error} onRetry={() => void reload()} />;
  if (!profile) {
    return (
      <EmptyState
        title="Load a company first"
        body="Complete intake so registration details have a company to attach to."
        action={<Button href="/onboarding">Start intake</Button>}
      />
    );
  }

  return (
    <div className="max-w-lg space-y-6">
      <PageHeader
        title="Company registration"
        description="SACI reviews the certificate you upload. This is not a call to a company register."
      />
      <Panel className="space-y-4">
      <p className="text-sm font-medium text-brand">Status: {STATUS[profile.company_verification_status] ?? humanize(profile.company_verification_status)}</p>
      <Field label="Legal name" value={legalName} onChange={(e) => setLegalName(e.target.value)} />
      <Field label="Registration number" value={number} onChange={(e) => setNumber(e.target.value)} />
      <Field label="Registrar" value={registrar} onChange={(e) => setRegistrar(e.target.value)} />
      <Select label="Country" value={country} onChange={(e) => setCountry(e.target.value)}>
        <option value="">Select</option>
        {COUNTRY_OPTIONS.map((c) => (
          <option key={c}>{c}</option>
        ))}
      </Select>
      <FileField
        label="Registration certificate"
        hint="PDF preferred."
        accept=".pdf,.png,.jpg,.jpeg"
        onFile={(f) => {
          setFile(f);
          toast.message(`${f.name} ready to submit.`);
        }}
      />
      {formError ? <p className="text-sm text-fail">{formError}</p> : null}
      <Button
        type="button"
        loading={busy}
        onClick={async () => {
          if (!legalName.trim() || !number.trim() || !country) {
            setFormError("Legal name, number, and country are required.");
            return;
          }
          setFormError(null);
          setBusy(true);
          try {
            const geo = COUNTRY_TO_CODE[country];
            await api.updateProfile(profile.id, {
              ...(geo ? { country: geo.code, currency: geo.currency } : {}),
              fields: {
                legal_name: { value: legalName, source: "founder" },
                registration_number: { value: number, source: "founder" },
                registrar: { value: registrar, source: "founder" },
              },
            });
            if (file) {
              const ticket = await api.beginDocumentUpload(profile.id, {
                kind: "registration_certificate",
                filename: file.name,
                content_type: file.type || "application/pdf",
              });
              await putFile(ticket.upload_url, file);
              await api.completeDocument(ticket.document_id);
            }
            await api.submitCompanyVerification(profile.id);
            toast.success("Submitted for review.");
            await reload();
          } catch (err) {
            toast.error(err instanceof Error ? err.message : "Could not submit.");
          } finally {
            setBusy(false);
          }
        }}
      >
        Submit for review
      </Button>
      </Panel>
    </div>
  );
}
