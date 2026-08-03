/**
 * The entitlement gates in `domain/access.ts`.
 *
 * The *order* the gates fire in is the thing under test. Telling someone to
 * verify their company when their trial has already expired is the wrong
 * instruction — verifying would not unlock anything — and the only place that
 * ordering is expressed is `gate()`.
 */

import {
  daysLeftInTrial,
  gate,
  hasAccess,
  investorGate,
  isPaid,
  lockExplanation,
  trialActive,
  type FounderCapability,
} from '@/domain/access';
import type { FounderAccount, InvestorAccount } from '@/domain/types';

const NOW = Date.parse('2026-07-31T12:00:00Z');
const inDays = (n: number) => new Date(NOW + n * 86_400_000).toISOString();

function founder(overrides: Partial<FounderAccount> = {}): FounderAccount {
  return {
    emailVerified: true,
    companyName: 'Northwind Labs',
    verification: 'verified',
    registration: null,
    trialEndsAt: inDays(7),
    subscriptionStatus: 'none',
    ...overrides,
  } as FounderAccount;
}

function investor(overrides: Partial<InvestorAccount> = {}): InvestorAccount {
  return {
    emailVerified: true,
    verification: 'verified',
    credentials: null,
    ...overrides,
  } as InvestorAccount;
}

const GATED: FounderCapability[] = ['aiMentor', 'investorVisibility', 'investorRequests'];

describe('founder gates', () => {
  it('allows a verified founder inside the trial', () => {
    for (const capability of GATED) {
      expect(gate(founder(), capability, NOW)).toEqual({ allowed: true, reason: null });
    }
  });

  it('asks for the email first, because it is the cheapest thing to fix', () => {
    // Unconfirmed email *and* an unverified company: the instruction must be
    // the email one, not "send us your certificate".
    const account = founder({ emailVerified: false, verification: 'unverified' });
    expect(gate(account, 'aiMentor', NOW).reason).toBe('email');
  });

  it('reports an expired trial as payment, never as verification', () => {
    // Verifying the company would not unlock anything here — the whole product
    // is locked until it is paid for.
    const account = founder({ trialEndsAt: inDays(-1), verification: 'unverified' });
    expect(gate(account, 'aiMentor', NOW).reason).toBe('payment');
  });

  it('gates on verification once email and payment are satisfied', () => {
    const account = founder({ verification: 'in_review' });
    for (const capability of GATED) {
      expect(gate(account, capability, NOW).reason).toBe('verification');
    }
  });

  it('leaves browsing your own account open while unverified', () => {
    const account = founder({ emailVerified: false, verification: 'unverified' });
    expect(gate(account, 'programmes', NOW).allowed).toBe(true);
    expect(gate(account, 'reassess', NOW).allowed).toBe(true);
  });

  it('treats a paid account as having access after the trial ends', () => {
    const account = founder({ trialEndsAt: inDays(-30), subscriptionStatus: 'active' });
    expect(isPaid(account)).toBe(true);
    expect(hasAccess(account, NOW)).toBe(true);
    expect(gate(account, 'aiMentor', NOW).allowed).toBe(true);
  });

  it('does not treat past_due or canceled as paid', () => {
    for (const status of ['past_due', 'canceled', 'none'] as const) {
      const account = founder({ trialEndsAt: inDays(-1), subscriptionStatus: status });
      expect(gate(account, 'aiMentor', NOW).reason).toBe('payment');
    }
  });

  it('counts the trial in whole days and floors at zero', () => {
    expect(daysLeftInTrial(founder({ trialEndsAt: inDays(7) }), NOW)).toBe(7);
    expect(daysLeftInTrial(founder({ trialEndsAt: inDays(-3) }), NOW)).toBe(0);
    expect(trialActive(founder({ trialEndsAt: inDays(-3) }), NOW)).toBe(false);
  });

  it('has copy for every reason it can return', () => {
    for (const reason of ['email', 'payment', 'verification'] as const) {
      expect(lockExplanation(reason).length).toBeGreaterThan(10);
    }
  });
});

describe('investor gates', () => {
  it('needs the address confirmed before the credentials', () => {
    const account = investor({ emailVerified: false, verification: 'unverified' });
    expect(investorGate(account, 'requestIntroduction').reason).toBe('email');
  });

  it('refuses an unverified investor and allows a verified one', () => {
    expect(investorGate(investor({ verification: 'in_review' }), 'scheduleCall').reason).toBe(
      'verification',
    );
    expect(investorGate(investor(), 'scheduleCall').allowed).toBe(true);
  });
});
