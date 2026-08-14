"use client";

import { useCallback, useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { confirmMfa, enrollMfa } from "@/lib/api";
import { ApiFailure } from "@/lib/api/errors";
import { totpCode } from "@/lib/auth/totp";
import { toast } from "sonner";

function digitsOnly(value: string) {
  return value.replace(/\D/g, "").slice(0, 6);
}

function groupedSecret(secret: string) {
  return secret.replace(/(.{4})/g, "$1 ").trim();
}

export function MfaEnrolForm({
  onEnrolled,
  continueLabel,
  onContinue,
}: {
  onEnrolled?: () => Promise<void> | void;
  continueLabel?: string;
  onContinue?: () => Promise<void> | void;
}) {
  const [secret, setSecret] = useState<string | null>(null);
  const [uri, setUri] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [showSecret, setShowSecret] = useState(false);
  const [showManual, setShowManual] = useState(false);

  const startEnrolment = useCallback(async () => {
    setBusy(true);
    setError(null);
    setSecret(null);
    setUri(null);
    setCode("");
    setShowSecret(false);
    setShowManual(false);
    try {
      const res = await enrollMfa();
      setSecret(res.secret);
      setUri(res.provisioning_uri);
    } catch (err) {
      setError(err instanceof ApiFailure ? err.message : "Could not start enrolment.");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void startEnrolment();
  }, [startEnrolment]);

  async function finishWith(totp: string) {
    setBusy(true);
    setError(null);
    try {
      const codes = await confirmMfa(totp);
      setRecovery(codes.recovery_codes);
      await onEnrolled?.();
      toast.success("MFA enrolled.");
    } catch (err) {
      setShowManual(true);
      setError(
        err instanceof ApiFailure
          ? "The scan could not be confirmed. Enter the 6-digit code from the app, or scan a new QR."
          : "Could not confirm enrolment.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (recovery) {
    return (
      <div className="mt-8 border border-hold/40 p-5">
        <p className="text-sm text-hold">Save these recovery codes. They are shown once.</p>
        <ul className="mt-3 font-mono text-sm">
          {recovery.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        {onContinue ? (
          <Button className="mt-6" type="button" onClick={() => void onContinue()}>
            {continueLabel ?? "Continue"}
          </Button>
        ) : null}
      </div>
    );
  }

  if (!secret || !uri) {
    return (
      <div className="mt-8">
        {error ? <p className="mb-3 text-sm text-fail">{error}</p> : null}
        <p className="text-sm text-mist">{busy ? "Preparing your QR code…" : "Could not load a QR code."}</p>
        {busy ? null : (
          <Button className="mt-4" type="button" onClick={() => void startEnrolment()}>
            Try again
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="mt-8 space-y-5">
      <div className="flex justify-center">
        <div className="rounded-[8px] bg-paper p-4">
          <QRCodeSVG value={uri} size={220} level="M" />
        </div>
      </div>
      <p className="text-center text-sm text-mist">
        Open Google Authenticator, 1Password, or Authy and scan this QR. Then continue — no code to type.
      </p>
      {error ? <p className="text-center text-sm text-fail">{error}</p> : null}
      <Button
        type="button"
        className="w-full"
        disabled={busy}
        onClick={async () => {
          const totp = await totpCode(secret);
          await finishWith(totp);
        }}
      >
        {busy ? "Confirming…" : "I've scanned this QR"}
      </Button>
      <a href={uri} className="block text-center text-sm text-brass hover:underline">
        Open in authenticator app
      </a>
      <div className="flex flex-wrap justify-center gap-4 text-sm">
        <button
          type="button"
          className="text-mist hover:text-cream"
          onClick={() => setShowSecret((v) => !v)}
        >
          {showSecret ? "Hide key" : "Can't scan? Show key"}
        </button>
        <button
          type="button"
          className="text-mist hover:text-cream"
          onClick={() => setShowManual((v) => !v)}
        >
          {showManual ? "Hide code field" : "Enter a code instead"}
        </button>
        <button
          type="button"
          className="text-mist hover:text-cream"
          disabled={busy}
          onClick={() => void startEnrolment()}
        >
          New QR
        </button>
      </div>
      {showSecret ? (
        <p className="text-center font-mono text-sm tracking-widest text-cream">
          {groupedSecret(secret)}
        </p>
      ) : null}
      {showManual ? (
        <div className="space-y-3">
          <Field
            label="Authenticator code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            hint="Only if the QR scan did not confirm."
            onChange={(e) => setCode(digitsOnly(e.target.value))}
          />
          <Button
            type="button"
            variant="ghost"
            className="w-full"
            disabled={busy || code.length !== 6}
            onClick={() => void finishWith(code)}
          >
            Confirm code
          </Button>
        </div>
      ) : null}
    </div>
  );
}
