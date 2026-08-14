"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { useSession } from "@/stores/session";
import { landingAfterAuth } from "@/lib/domain/onboarding";

export default function SignInPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next");
  const verified = searchParams.get("verified") === "1";
  const signIn = useSession((s) => s.signIn);
  const busy = useSession((s) => s.busy);
  const error = useSession((s) => s.error);
  const [email, setEmail] = useState(searchParams.get("email") ?? "");
  const [password, setPassword] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const session = await signIn(email.trim(), password);
    if (session) {
      router.replace(await landingAfterAuth(session, next));
      return;
    }
    if (useSession.getState().mfaToken) router.push("/mfa");
  }

  return (
    <div>
      <p className="text-[11px] font-extrabold tracking-[0.18em] text-brass">
        {verified ? "EMAIL CONFIRMED" : "SIGN IN"}
      </p>
      <h1 className="mt-3 font-display text-4xl text-cream">
        {verified ? "Sign in to continue." : "Welcome back."}
      </h1>
      <p className="mt-2 text-sm text-mist">
        {verified
          ? "Your address is confirmed. Use the password you chose at sign-up."
          : "The role is already on the account."}
      </p>
      <form onSubmit={submit} className="mt-8 space-y-3">
        <Field
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Field
          label="Password"
          type="password"
          autoComplete="current-password"
          value={password}
          error={error}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button type="submit" disabled={busy} className="mt-4 w-full">
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <div className="mt-6 flex justify-between text-sm text-mist">
        <Link href="/forgot-password" className="hover:text-cream">
          Forgot password
        </Link>
        <Link href="/sign-up" className="hover:text-cream">
          Create an account
        </Link>
      </div>
    </div>
  );
}
