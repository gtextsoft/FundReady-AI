export const TRIAL_DAYS = 14;

export type FounderCapability =
  | "aiMentor"
  | "investorVisibility"
  | "investorRequests"
  | "programmes"
  | "reassess";

export type InvestorCapability =
  | "browseDealflow"
  | "requestIntroduction"
  | "scheduleCall"
  | "expressInterest";
export type GateReason = "email" | "payment" | "verification";
export type Gate = { allowed: true; reason: null } | { allowed: false; reason: GateReason };

const ALLOW: Gate = { allowed: true, reason: null };
const deny = (reason: GateReason): Gate => ({ allowed: false, reason });

export type FounderAccount = {
  emailVerified: boolean;
  trialEndsAt: string;
  subscriptionStatus: "none" | "active" | "past_due" | "canceled";
  hasAccess?: boolean;
};

export type InvestorAccount = {
  emailVerified: boolean;
  verification: "unverified" | "in_review" | "verified" | "rejected";
};

export function hasAccess(account: FounderAccount, now: number = Date.now()): boolean {
  if (typeof account.hasAccess === "boolean") return account.hasAccess;
  if (account.subscriptionStatus === "active") return true;
  return new Date(account.trialEndsAt).getTime() > now;
}

export function daysLeftInTrial(account: FounderAccount, now: number = Date.now()): number {
  const ms = new Date(account.trialEndsAt).getTime() - now;
  return Math.max(0, Math.ceil(ms / 86_400_000));
}

const NEEDS_EMAIL = new Set<FounderCapability>([
  "aiMentor",
  "investorVisibility",
  "investorRequests",
]);

export function gate(
  account: FounderAccount,
  capability: FounderCapability,
  now: number = Date.now(),
): Gate {
  if (NEEDS_EMAIL.has(capability) && !account.emailVerified) return deny("email");
  if (!hasAccess(account, now)) return deny("payment");
  return ALLOW;
}

export function investorGate(account: InvestorAccount, capability: InvestorCapability): Gate {
  void capability;
  if (!account.emailVerified) return deny("email");
  return ALLOW;
}

export function gateCopy(reason: GateReason | null, side: "founder" | "investor" = "founder") {
  if (reason === "email") {
    return {
      title: "Confirm your email",
      body:
        side === "founder"
          ? "Needed before you can save audits, upload documents, or publish."
          : "Needed before you can express interest or request introductions.",
      cta: "Confirm email",
    };
  }
  if (reason === "payment") {
    return {
      title: "Unlock FundReady AI",
      body: "Your free trial has ended. One payment restores full access.",
      cta: "View unlock",
    };
  }
  if (reason === "verification") {
    return {
      title: "Add registration details",
      body: "Optional for browsing — required before some publish and diligence steps.",
      cta: "Add registration",
    };
  }
  return { title: "Continue", body: "You have access to this feature.", cta: "Open" };
}

export const UNLOCK_PRICE = {
  currency: "USD",
  symbol: "$",
  amount: 149,
  label: "$149",
  cadence: "one-time",
} as const;

export const UNLOCK_BENEFITS = [
  "Listed in the investor dealflow database",
  "Unlimited AI mentor sessions on your metrics",
  "Accept introductions and virtual calls from investors",
  "Re-run your Fundability assessment any time",
  "Both growth programmes, for as long as you need them",
];

export const MIN_PASSWORD = 12;
export const PASSWORD_HINT = `At least ${MIN_PASSWORD} characters.`;

export function checkPassword(password: string, confirmation?: string) {
  if (!password) return { ok: false, message: "Choose a password." };
  if (password.length < MIN_PASSWORD)
    return { ok: false, message: `Use at least ${MIN_PASSWORD} characters.` };
  if (confirmation !== undefined && confirmation !== "" && confirmation !== password)
    return { ok: false, message: "Both passwords must match." };
  return { ok: true, message: null as string | null };
}
