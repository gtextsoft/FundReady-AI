export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

export function founderAccount(session: {
  emailVerified: boolean;
  trialEndsAt: string;
  subscriptionStatus: "none" | "active" | "past_due" | "canceled";
  hasAccess?: boolean;
} | null) {
  return {
    emailVerified: session?.emailVerified ?? false,
    trialEndsAt: session?.trialEndsAt ?? "",
    subscriptionStatus: session?.subscriptionStatus ?? "none" as const,
    hasAccess: session?.hasAccess,
  };
}

export function investorAccount(session: {
  emailVerified: boolean;
  kycStatus?: "none" | "pending" | "verified" | "failed";
} | null) {
  const kyc = session?.kycStatus;
  return {
    emailVerified: session?.emailVerified ?? false,
    verification:
      kyc === "verified"
        ? ("verified" as const)
        : kyc === "pending"
          ? ("in_review" as const)
          : kyc === "failed"
            ? ("rejected" as const)
            : ("unverified" as const),
  };
}
