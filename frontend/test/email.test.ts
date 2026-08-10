/**
 * The founder company-domain rule in `domain/email.ts`.
 *
 * The asymmetry is the point: **a false reject turns away a real founder**,
 * which costs more than letting an unusual domain through — the company is
 * verified properly later. So the tests below care much more about the
 * addresses that must be accepted than about exhaustively listing blocked ones.
 */

import {
  checkEmail,
  checkFounderEmail,
  companyNameFromDomain,
  companyNameFromEmail,
  emailDomain,
  isPersonalEmailDomain,
} from '@/domain/email';

describe('personal domains', () => {
  it('rejects the major consumer providers', () => {
    for (const d of ['gmail.com', 'yahoo.com', 'outlook.com', 'icloud.com', 'proton.me', 'qq.com']) {
      expect(isPersonalEmailDomain(d)).toBe(true);
    }
  });

  it('rejects country variants without enumerating them', () => {
    for (const d of ['yahoo.co.uk', 'hotmail.fr', 'live.com.au', 'gmx.at']) {
      expect(isPersonalEmailDomain(d)).toBe(true);
    }
  });

  it('rejects subdomains of a consumer provider', () => {
    expect(isPersonalEmailDomain('mail.yahoo.com')).toBe(true);
  });

  it('rejects disposable services', () => {
    for (const d of ['mailinator.com', 'yopmail.com', 'maildrop.cc']) {
      expect(isPersonalEmailDomain(d)).toBe(true);
    }
  });

  it('accepts ordinary company domains, including unusual ones', () => {
    // These are the expensive failures: each one is a real founder turned away.
    for (const d of [
      'northwind-labs.com',
      'kanmi.ng',
      'acme.co.uk',
      'startup.xyz',
      'a-very-new-tld.ventures',
      'mail.northwind-labs.com',
      'gmail-competitor.com',
    ]) {
      expect(isPersonalEmailDomain(d)).toBe(false);
    }
  });

  it('is case and whitespace insensitive', () => {
    expect(isPersonalEmailDomain('  GMAIL.COM ')).toBe(true);
  });
});

describe('checkFounderEmail', () => {
  it('names the domain in the refusal, so the message is actionable', () => {
    const result = checkFounderEmail('ada@gmail.com');
    expect(result.ok).toBe(false);
    expect(result.issue).toBe('personal');
    expect(result.message).toContain('gmail.com');
  });

  it('distinguishes empty from malformed from personal', () => {
    expect(checkFounderEmail('  ').issue).toBe('empty');
    expect(checkFounderEmail('not-an-email').issue).toBe('invalid');
    expect(checkFounderEmail('ada@gmail.com').issue).toBe('personal');
    expect(checkFounderEmail('ada@northwind-labs.com').issue).toBeNull();
  });

  it('applies only the shape rule to investors', () => {
    // Angels legitimately operate from personal addresses.
    expect(checkEmail('angel@gmail.com').ok).toBe(true);
    expect(checkEmail('angel@').ok).toBe(false);
  });
});

describe('companyNameFromDomain', () => {
  it('turns a domain into a plausible display name', () => {
    expect(companyNameFromDomain('northwind-labs.com')).toBe('Northwind Labs');
    expect(companyNameFromEmail('ada@kanmi.ng')).toBe('Kanmi');
  });

  it('sees through a two-label public suffix', () => {
    // Without the suffix list this yields "Co", which is nobody's company.
    expect(companyNameFromDomain('acme.co.uk')).toBe('Acme');
    expect(companyNameFromDomain('kanmi.com.ng')).toBe('Kanmi');
  });

  it('takes the company label out of a subdomain', () => {
    expect(companyNameFromDomain('mail.northwind.com')).toBe('Northwind');
  });

  it('returns nothing for a personal mailbox, rather than "Gmail"', () => {
    expect(companyNameFromDomain('gmail.com')).toBe('');
    expect(companyNameFromEmail('ada@yahoo.co.uk')).toBe('');
  });

  it('returns nothing rather than guessing from a bare label', () => {
    expect(companyNameFromDomain('localhost')).toBe('');
    expect(companyNameFromDomain('')).toBe('');
  });
});

describe('emailDomain', () => {
  it('lowercases and trims', () => {
    expect(emailDomain('  Ada@Northwind-Labs.COM ')).toBe('northwind-labs.com');
  });

  it('returns an empty string when there is no domain', () => {
    expect(emailDomain('ada')).toBe('');
  });
});
