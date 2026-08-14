"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { ApiFailure, resendVerification, verifyEmail } from "@/lib/api";
import { useRouter } from "next/navigation";

function digitsOnly(value: string) {
  return value.replace(/\D/g, "").slice(0, 6);
}

export default function VerifyEmailPage() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [resent, setResent] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await verifyEmail(email.trim(), digitsOnly(code));
      const next = new URLSearchParams();
      next.set("verified", "1");
      if (email.trim()) next.set("email", email.trim());
      const dest = params.get("next");
      if (dest && dest.startsWith("/") && !dest.startsWith("//")) {
        next.set("next", dest);
      }
      router.replace(`/sign-in?${next.toString()}`);
    } catch (err) {
      setError(err instanceof ApiFailure ? err.message : "That code was not accepted.");
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 className="font-display text-4xl text-cream">Confirm your email.</h1>
      <p className="mt-2 text-sm text-mist">
        Enter the six-digit code we sent. Nothing in that message is a clickable link.
      </p>
      <form onSubmit={submit} className="mt-8 space-y-3">
        <Field label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <Field
          label="Code"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          value={code}
          onChange={(e) => setCode(digitsOnly(e.target.value))}
        />
        {error ? <p className="text-sm text-fail">{error}</p> : null}
        <Button type="submit" disabled={busy || code.length !== 6} className="mt-4 w-full">
          {busy ? "Confirming…" : "Confirm email"}
        </Button>
      </form>
      <button
        type="button"
        className="mt-4 text-sm text-mist hover:text-cream"
        onClick={async () => {
          setResent(true);
          try {
            await resendVerification(email.trim());
          } catch {
            /* uniform 202 — do not claim an email went out */
          }
        }}
      >
        {resent ? "If that address can be verified, another code is on its way." : "Resend code"}
      </button>
      <p className="mt-6 text-sm text-mist">
        <Link href="/sign-in" className="hover:text-cream">
          Back to sign in
        </Link>
      </p>
    </div>
  );
}
