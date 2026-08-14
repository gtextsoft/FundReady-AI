"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { ApiFailure, requestPasswordReset } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await requestPasswordReset(email.trim());
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiFailure ? err.message : "Could not start a reset.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 className="font-display text-4xl text-cream">Reset your password.</h1>
      <p className="mt-2 text-sm text-mist">
        If that address has an account, a six-digit code is on its way. We will not tell you which.
      </p>
      {done ? (
        <p className="mt-8 text-sm text-cream">
          Continue at{" "}
          <Link href="/reset-password" className="text-brass">
            reset password
          </Link>{" "}
          with the code.
        </p>
      ) : (
        <form onSubmit={submit} className="mt-8 space-y-3">
          <Field label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          {error ? <p className="text-sm text-fail">{error}</p> : null}
          <Button type="submit" disabled={busy} className="mt-4 w-full">
            {busy ? "Sending…" : "Send code"}
          </Button>
        </form>
      )}
    </div>
  );
}
