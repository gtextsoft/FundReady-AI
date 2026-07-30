/**
 * Founder sign-up requires a company email address.
 *
 * There is no way to positively identify a "company" domain, so this works the
 * other way round: a curated list of consumer mailbox providers and disposable
 * services is rejected, and everything else is accepted. That is deliberate —
 * a false reject turns a real founder away at the door, which is far more
 * costly than letting an unusual domain through. Company registration is
 * verified properly later anyway (see `domain/access.ts`).
 *
 * Investors are NOT held to this rule: angels legitimately operate from
 * personal addresses.
 */

/** Consumer mailbox providers, by exact domain. */
const PERSONAL_DOMAINS = new Set([
  // Google
  'gmail.com', 'googlemail.com',
  // Yahoo
  'yahoo.com', 'ymail.com', 'rocketmail.com',
  // Microsoft
  'hotmail.com', 'outlook.com', 'live.com', 'msn.com', 'passport.com',
  // AOL
  'aol.com', 'aim.com',
  // Apple
  'icloud.com', 'me.com', 'mac.com',
  // Privacy-first providers
  'protonmail.com', 'protonmail.ch', 'proton.me', 'pm.me',
  'tutanota.com', 'tutanota.de', 'tuta.io', 'hushmail.com',
  'duck.com', 'hey.com',
  // General consumer webmail
  'zoho.com', 'zohomail.com', 'yandex.com', 'yandex.ru', 'mail.ru',
  'mail.com', 'email.com', 'usa.com', 'inbox.com',
  'gmx.com', 'gmx.net', 'gmx.de', 'web.de', 't-online.de', 'freenet.de',
  'fastmail.com', 'fastmail.fm',
  // Asia
  'qq.com', '163.com', '126.com', 'sina.com', 'sohu.com',
  'naver.com', 'hanmail.net', 'daum.net',
  'rediffmail.com', 'sify.com', 'indiatimes.com',
  // Europe
  'orange.fr', 'wanadoo.fr', 'free.fr', 'laposte.net', 'sfr.fr',
  'libero.it', 'virgilio.it', 'tiscali.it', 'alice.it',
  // Africa & Latin America
  'mweb.co.za', 'vodamail.co.za', 'webmail.co.za', 'telkomsa.net',
  'bol.com.br', 'uol.com.br', 'terra.com.br', 'ig.com.br',
  // Disposable / throwaway
  'mailinator.com', 'yopmail.com', 'guerrillamail.com', '10minutemail.com',
  'temp-mail.org', 'throwawaymail.com', 'trashmail.com', 'sharklasers.com',
  'getnada.com', 'dispostable.com', 'maildrop.cc', 'mintemail.com',
]);

/**
 * Brands with too many country domains to enumerate — `yahoo.co.uk`,
 * `hotmail.fr`, `live.com.au` and so on.
 */
const PERSONAL_PREFIXES = ['yahoo.', 'hotmail.', 'outlook.', 'live.', 'gmx.', 'googlemail.'];

/** Loose on purpose: real addresses fail strict RFC regexes more often than fakes pass. */
const EMAIL_SHAPE = /^[^\s@]+@[^\s@.]+(\.[^\s@.]+)+$/;

export function emailDomain(email: string): string {
  return email.trim().toLowerCase().split('@')[1] ?? '';
}

export function isValidEmail(email: string): boolean {
  return EMAIL_SHAPE.test(email.trim());
}

export function isPersonalEmailDomain(domain: string): boolean {
  const d = domain.trim().toLowerCase();
  if (!d) return false;
  if (PERSONAL_DOMAINS.has(d)) return true;
  if (PERSONAL_PREFIXES.some((p) => d.startsWith(p))) return true;
  // Subdomains of a consumer provider, e.g. mail.yahoo.com.
  return [...PERSONAL_DOMAINS].some((known) => d.endsWith(`.${known}`));
}

/**
 * Public suffixes that are two labels long, so `acme.co.uk` yields "Acme" and
 * not "Co". Not the full Public Suffix List — that is a large, churning dataset
 * and this only needs to cover the markets in `founder/verify.tsx` plus the
 * common anglophone ones. An unlisted suffix degrades to taking one label,
 * which is a slightly wrong suggestion, not a broken sign-up.
 */
const MULTIPART_SUFFIXES = [
  'co.uk', 'org.uk', 'ac.uk', 'gov.uk', 'me.uk', 'ltd.uk', 'plc.uk',
  'com.ng', 'org.ng', 'gov.ng', 'edu.ng',
  'co.za', 'org.za', 'net.za',
  'co.ke', 'or.ke', 'go.ke',
  'com.gh', 'com.au', 'net.au', 'org.au',
  'com.br', 'com.sg', 'com.my', 'com.hk', 'com.tr', 'com.mx', 'com.ar',
  'co.in', 'net.in', 'org.in', 'co.jp', 'co.kr', 'co.nz', 'co.il',
  'com.cn', 'com.pk', 'com.eg', 'com.sa', 'com.ae',
];

/**
 * A best-guess company name from an email domain: `ada@northwind-labs.com`
 * becomes "Northwind Labs".
 *
 * This is a **suggestion to save typing**, never an identity claim. The real
 * legal name is whatever the founder enters and whatever the registry confirms
 * at verification — this is only a default they can overwrite. Returns an empty
 * string for personal mailboxes, so nobody is told their company is "Gmail".
 */
export function companyNameFromDomain(domain: string): string {
  const d = domain.trim().toLowerCase().replace(/^www\./, '');
  if (!d || isPersonalEmailDomain(d)) return '';

  const labels = d.split('.').filter(Boolean);
  if (labels.length < 2) return '';

  const suffix = MULTIPART_SUFFIXES.find((s) => d.endsWith(`.${s}`));
  // Drop the public suffix, then take the rightmost remaining label, so a
  // subdomain like `mail.northwind.com` still resolves to "northwind".
  const remaining = suffix ? labels.slice(0, -suffix.split('.').length) : labels.slice(0, -1);
  const name = remaining.at(-1) ?? '';
  if (!name) return '';

  return name
    .split(/[-_]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/** Convenience wrapper: the same guess, straight from a full address. */
export function companyNameFromEmail(email: string): string {
  return companyNameFromDomain(emailDomain(email));
}

export type EmailIssue = 'empty' | 'invalid' | 'personal' | null;

export type EmailCheck = { ok: boolean; issue: EmailIssue; message: string | null; domain: string };

const OK: EmailCheck = { ok: true, issue: null, message: null, domain: '' };

/**
 * Gate for founder sign-up. Investors should use `checkEmail` instead, which
 * applies the shape rule only.
 */
export function checkFounderEmail(email: string): EmailCheck {
  const trimmed = email.trim();
  const domain = emailDomain(trimmed);

  if (!trimmed) return { ok: false, issue: 'empty', message: 'Enter your work email address.', domain: '' };
  if (!isValidEmail(trimmed))
    return { ok: false, issue: 'invalid', message: 'That does not look like an email address.', domain };
  if (isPersonalEmailDomain(domain))
    return {
      ok: false,
      issue: 'personal',
      message: `Use your company email, not a personal ${domain} address. Investors need to see you at your own domain.`,
      domain,
    };

  return { ...OK, domain };
}

/** Shape check only — used for investor sign-up and for login on both sides. */
export function checkEmail(email: string): EmailCheck {
  const trimmed = email.trim();
  const domain = emailDomain(trimmed);
  if (!trimmed) return { ok: false, issue: 'empty', message: 'Enter your email address.', domain: '' };
  if (!isValidEmail(trimmed))
    return { ok: false, issue: 'invalid', message: 'That does not look like an email address.', domain };
  return { ...OK, domain };
}
