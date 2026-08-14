"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { checkEmail, checkFounderEmail } from "@/lib/domain/email";
import { checkPassword, PASSWORD_HINT } from "@/lib/domain/access";
import { ApiFailure, register } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function SignUpPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const role = searchParams.get("role") === "investor" ? "investor" : "founder";

  function selectRole(next: "founder" | "investor") {
    const params = new URLSearchParams(searchParams.toString());
    params.set("role", next);
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  }
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const emailCheck = role === "founder" ? checkFounderEmail(email) : checkEmail(email);
    if (!emailCheck.ok) {
      setError(emailCheck.message);
      return;
    }
    const pw = checkPassword(password, confirm);
    if (!pw.ok) {
      setError(pw.message);
      return;
    }
    if (!first.trim() || !last.trim()) {
      setError("Enter your first and last name.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await register({
        email: email.trim(),
        password,
        role,
        first_name: first.trim(),
        last_name: last.trim(),
      });
      const next = role === "founder" ? "/onboarding" : "/investor";
      router.push(`/verify-email?email=${encodeURIComponent(email.trim())}&next=${next}`);
    } catch (err) {
      setError(err instanceof ApiFailure ? err.message : "Could not create the account.");
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 className="font-display text-4xl text-cream">
        {role === "founder" ? "Get funded on evidence, not vibes." : "Back companies on evidence, not vibes."}
      </h1>
      <div className="mt-6 grid grid-cols-2 border border-line" role="tablist" aria-label="Account type">
        {(["founder", "investor"] as const).map((r) => (
          <button
            key={r}
            type="button"
            role="tab"
            aria-selected={role === r}
            onClick={() => selectRole(r)}
            className={cn(
              "min-h-11 py-2.5 text-sm capitalize",
              role === r ? "bg-brass text-brass-ink" : "text-mist hover:text-cream",
            )}
          >
            {r}
          </button>
        ))}
      </div>
      <form onSubmit={submit} className="mt-6 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="First name" value={first} onChange={(e) => setFirst(e.target.value)} />
          <Field label="Last name" value={last} onChange={(e) => setLast(e.target.value)} />
        </div>
        <Field
          label={role === "founder" ? "Work email" : "Email"}
          type="email"
          value={email}
          autoComplete="email"
          onChange={(e) => setEmail(e.target.value)}
        />
        <Field
          label="Password"
          type="password"
          hint={PASSWORD_HINT}
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Field
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        {error ? (
          <p className="text-sm text-fail" role="alert">
            {error}
          </p>
        ) : null}
        <Button type="submit" disabled={busy} className="mt-4 w-full">
          {busy ? "Creating…" : "Create account"}
        </Button>
      </form>
      <p className="mt-6 text-sm text-mist">
        Already have an account?{" "}
        <Link href="/sign-in" className="text-cream hover:text-brass">
          Sign in
        </Link>
      </p>
    </div>
  );
}
