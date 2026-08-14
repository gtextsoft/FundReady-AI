"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { useSession } from "@/stores/session";
import { landingAfterAuth } from "@/lib/domain/onboarding";

export default function MfaPage() {
  const router = useRouter();
  const verifyMfa = useSession((s) => s.verifyMfa);
  const busy = useSession((s) => s.busy);
  const error = useSession((s) => s.error);
  const [code, setCode] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const session = await verifyMfa(code.trim());
    if (session) router.replace(await landingAfterAuth(session));
  }

  return (
    <div>
      <h1 className="font-display text-4xl text-cream">Second factor.</h1>
      <p className="mt-2 text-sm text-mist">
        Enter the six-digit authenticator code, or one recovery code.
      </p>
      <form onSubmit={submit} className="mt-8 space-y-3">
        <Field
          label="Code"
          autoComplete="one-time-code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
        />
        {error ? <p className="text-sm text-fail">{error}</p> : null}
        <Button type="submit" disabled={busy} className="mt-4 w-full">
          {busy ? "Checking…" : "Continue"}
        </Button>
      </form>
    </div>
  );
}
