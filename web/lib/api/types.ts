export type Role = "founder" | "investor" | "admin";

export type AccountStatus = "pending_verification" | "active" | "suspended";
export type KycStatus = "none" | "pending" | "verified" | "failed";
export type SubscriptionStatus = "none" | "active" | "past_due" | "canceled";

export type MeResponse = {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  role: Role;
  status: AccountStatus;
  email_verified: boolean;
  kyc_status: KycStatus;
  subscription_status: SubscriptionStatus;
  created_at: string;
  trial_ends_at: string;
  has_access: boolean;
  mfa_enabled: boolean;
};

export type Session = {
  userId: string;
  email: string;
  role: Role;
  firstName: string;
  lastName: string;
  displayName: string;
  emailVerified: boolean;
  status: AccountStatus;
  kycStatus: KycStatus;
  subscriptionStatus: SubscriptionStatus;
  trialEndsAt: string;
  hasAccess: boolean;
  mfaEnabled: boolean;
};

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
};
