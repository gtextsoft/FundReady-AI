import type { FounderAccount, InvestorAccount } from './types';

/**
 * Who may do what, and why not.
 *
 * Two independent gates sit in front of the founder product:
 *
 *   payment      — every founder gets 14 days of full access from signup.
 *                  When the window closes, a one-off unlock payment is
 *                  required and everything gated goes dark.
 *   verification — the company must be shown to be registered in its own
 *                  country before it can be surfaced to investors or use the
 *                  AI mentor. This gate applies during the trial too.
 *
 * Screens never re-derive these rules; they call `gate()` and render the
 * reason they get back.
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

export type InvestorCapability = 'requestIntroduction' | 'scheduleCall';

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

/** Capabilities that verification gates, regardless of payment state. */
const NEEDS_VERIFICATION: ReadonlySet<FounderCapability> = new Set<FounderCapability>([
  'aiMentor',
  'investorVisibility',
  'investorRequests',
]);

/**
 * Capabilities that a confirmed email address gates (AUTH.md): buying,
 * uploading, being discovered, and dealing with investors. Browsing your own
 * empty account is deliberately allowed while unverified, so `reassess` and
 * `programmes` stay open.
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
  // Email comes first. It is the cheapest thing to fix and it gates the same
  // actions company verification does, so telling someone to send us their
  // certificate while their address is unconfirmed is the wrong instruction.
  if (NEEDS_EMAIL.has(capability) && !account.emailVerified) return deny('email');
  // Then payment: an expired trial locks the whole product, so "verify your
  // company" would also be the wrong thing to say.
  if (!hasAccess(account, now)) return deny('payment');
  if (NEEDS_VERIFICATION.has(capability) && account.verification !== 'verified') return deny('verification');
  return ALLOW;
}

/** Investors confirm their address, then their credentials, before reaching a founder. */
export function investorGate(account: InvestorAccount, _capability: InvestorCapability): Gate {
  if (!account.emailVerified) return deny('email');
  return account.verification === 'verified' ? ALLOW : deny('verification');
}

/** Copy for a locked module tile. */
export function lockLabel(reason: GateReason): string {
  if (reason === 'payment') return 'Locked';
  return reason === 'email' ? 'Confirm email' : 'Verify to unlock';
}

export function lockExplanation(reason: GateReason): string {
  if (reason === 'payment') return 'Your free trial has ended. Unlock SACI FundMe to continue.';
  if (reason === 'email') return 'Confirm your email address to unlock this.';
  return 'Verify that your company is registered in your country to unlock this.';
}
