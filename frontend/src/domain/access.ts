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

export type GateReason = 'payment' | 'verification';

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

/** True when the founder has either paid or is still inside the trial window. */
export function hasAccess(account: FounderAccount, now: number = Date.now()): boolean {
  return account.paidAt !== null || trialActive(account, now);
}

/** Capabilities that verification gates, regardless of payment state. */
const NEEDS_VERIFICATION: ReadonlySet<FounderCapability> = new Set<FounderCapability>([
  'aiMentor',
  'investorVisibility',
  'investorRequests',
]);

export function gate(
  account: FounderAccount,
  capability: FounderCapability,
  now: number = Date.now(),
): Gate {
  // Payment is checked first: an expired trial locks the whole product, so
  // "verify your company" would be the wrong thing to tell someone.
  if (!hasAccess(account, now)) return deny('payment');
  if (NEEDS_VERIFICATION.has(capability) && account.verification !== 'verified') return deny('verification');
  return ALLOW;
}

/** Investors are only asked to verify before they can reach a founder. */
export function investorGate(account: InvestorAccount, _capability: InvestorCapability): Gate {
  return account.verification === 'verified' ? ALLOW : deny('verification');
}

/** Copy for a locked module tile. */
export function lockLabel(reason: GateReason): string {
  return reason === 'payment' ? 'Locked' : 'Verify to unlock';
}

export function lockExplanation(reason: GateReason): string {
  return reason === 'payment'
    ? 'Your free trial has ended. Unlock SACI FundMe to continue.'
    : 'Verify that your company is registered in your country to unlock this.';
}
