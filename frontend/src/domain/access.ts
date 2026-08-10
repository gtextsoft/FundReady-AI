import type { FounderAccount, InvestorAccount } from './types';

/**
 * Who may do what, and why not.
 *
 * Founder gates (aligned with what the server actually enforces today):
 *
 *   email     — confirm address before discovery / mentor / investor flows
 *   payment   — trial or paid subscription
 *
 * Company-registration verification used to gate mentor and visibility, but
 * there is no server status field for it yet — hardcoding `unverified` locked
 * the product forever. Visibility is now controlled by publish + readiness
 * gate on the server. Investor KYC still uses real `kyc_status`.
 */

export const TRIAL_DAYS = 14;

export type FounderCapability =
  | 'aiMentor'
  /** Whether the company appears in investor dealflow at all. */
  | 'investorVisibility'
  /** Accepting introductions and virtual-call requests. */
  | 'investorRequests'
  | 'programmes'
  | 'reassess';

export type InvestorCapability = 'requestIntroduction' | 'scheduleCall' | 'expressInterest';

export type GateReason = 'email' | 'payment' | 'verification';

export type Gate = { allowed: true; reason: null } | { allowed: false; reason: GateReason };

const ALLOW: Gate = { allowed: true, reason: null };
const deny = (reason: GateReason): Gate => ({ allowed: false, reason });

export function daysLeftInTrial(account: FounderAccount, now: number = Date.now()): number {
  const ms = new Date(account.trialEndsAt).getTime() - now;
  return Math.max(0, Math.ceil(ms / 86_400_000));
}

export function trialActive(account: FounderAccount, now: number = Date.now()): boolean {
  return new Date(account.trialEndsAt).getTime() > now;
}

/** True once the founder's access is paid for, per the server's Stripe state. */
export function isPaid(account: FounderAccount): boolean {
  return account.subscriptionStatus === 'active';
}

/** True when the founder has either paid or is still inside the trial window. */
export function hasAccess(account: FounderAccount, now: number = Date.now()): boolean {
  return isPaid(account) || trialActive(account, now);
}

/**
 * Capabilities that a confirmed email address gates (AUTH.md).
 * Browsing your own empty account stays open while unverified.
 */
const NEEDS_EMAIL: ReadonlySet<FounderCapability> = new Set<FounderCapability>([
  'aiMentor',
  'investorVisibility',
  'investorRequests',
]);

export function gate(
  account: FounderAccount,
  capability: FounderCapability,
  now: number = Date.now(),
): Gate {
  if (NEEDS_EMAIL.has(capability) && !account.emailVerified) return deny('email');
  if (!hasAccess(account, now)) return deny('payment');
  return ALLOW;
}

/**
 * Investors confirm email before brokerage actions.
 *
 * KYC (`verification`) is shown on profile but does not hard-block express
 * interest until Stripe Identity (T4.1) is live — otherwise the tab is a dead end.
 */
export function investorGate(account: InvestorAccount, capability: InvestorCapability): Gate {
  if (!account.emailVerified) return deny('email');
  if (capability === 'expressInterest') return ALLOW;
  return account.verification === 'verified' ? ALLOW : deny('verification');
}

/** Copy for a locked module tile. */
export function lockLabel(reason: GateReason): string {
  if (reason === 'payment') return 'Locked';
  return reason === 'email' ? 'Confirm email' : 'Verify to unlock';
}

export function lockExplanation(reason: GateReason): string {
  if (reason === 'payment') return 'Your free trial has ended. Unlock FundReady AI to continue.';
  if (reason === 'email') return 'Confirm your email address to unlock this.';
  return 'Complete investor verification when it becomes available.';
}
