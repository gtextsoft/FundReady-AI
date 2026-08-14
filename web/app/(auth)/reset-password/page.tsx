"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { checkPassword, PASSWORD_HINT } from "@/lib/domain/access";
import { ApiFailure, confirmPasswordReset } from "@/lib/api";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const pw = checkPassword(password, confirm);
    if (!pw.ok) {
      setError(pw.message);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await confirmPasswordReset(email.trim(), code.trim(), password);
      router.replace("/sign-in");
    } catch (err) {
      setError(err instanceof ApiFailure ? err.message : "Could not reset the password.");
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 className="font-display text-4xl text-cream">Choose a new password.</h1>
      <p className="mt-2 text-sm text-mist">
        Succeeding ends every session on every device. Sign in again afterwards.
      </p>
      <form onSubmit={submit} className="mt-8 space-y-3">
        <Field label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <Field label="Code" value={code} onChange={(e) => setCode(e.target.value)} />
        <Field
          label="New password"
          type="password"
          hint={PASSWORD_HINT}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Field
          label="Confirm"
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        {error ? <p className="text-sm text-fail">{error}</p> : null}
        <Button type="submit" disabled={busy} className="mt-4 w-full">
          {busy ? "Saving…" : "Reset password"}
        </Button>
      </form>
    </div>
  );
}
