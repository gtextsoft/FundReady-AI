const PERSONAL_DOMAINS = new Set([
  "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "rocketmail.com",
  "hotmail.com", "outlook.com", "live.com", "msn.com", "passport.com",
  "aol.com", "aim.com", "icloud.com", "me.com", "mac.com",
  "protonmail.com", "protonmail.ch", "proton.me", "pm.me",
  "tutanota.com", "tutanota.de", "tuta.io", "hushmail.com",
  "duck.com", "hey.com", "zoho.com", "zohomail.com", "yandex.com", "yandex.ru", "mail.ru",
  "mail.com", "email.com", "usa.com", "inbox.com",
  "gmx.com", "gmx.net", "gmx.de", "web.de", "t-online.de", "freenet.de",
  "fastmail.com", "fastmail.fm", "qq.com", "163.com", "126.com", "sina.com", "sohu.com",
  "naver.com", "hanmail.net", "daum.net", "rediffmail.com", "sify.com", "indiatimes.com",
  "orange.fr", "wanadoo.fr", "free.fr", "laposte.net", "sfr.fr",
  "libero.it", "virgilio.it", "tiscali.it", "alice.it",
  "mweb.co.za", "vodamail.co.za", "webmail.co.za", "telkomsa.net",
  "bol.com.br", "uol.com.br", "terra.com.br", "ig.com.br",
  "mailinator.com", "yopmail.com", "guerrillamail.com", "10minutemail.com",
  "temp-mail.org", "throwawaymail.com", "trashmail.com", "sharklasers.com",
  "getnada.com", "dispostable.com", "maildrop.cc", "mintemail.com",
]);

const PERSONAL_PREFIXES = ["yahoo.", "hotmail.", "outlook.", "live.", "gmx.", "googlemail."];
const EMAIL_SHAPE = /^[^\s@]+@[^\s@.]+(\.[^\s@.]+)+$/;

export function emailDomain(email: string): string {
  return email.trim().toLowerCase().split("@")[1] ?? "";
}

export function isValidEmail(email: string): boolean {
  return EMAIL_SHAPE.test(email.trim());
}

export function isPersonalEmailDomain(domain: string): boolean {
  const d = domain.trim().toLowerCase();
  if (!d) return false;
  if (PERSONAL_DOMAINS.has(d)) return true;
  if (PERSONAL_PREFIXES.some((p) => d.startsWith(p))) return true;
  return [...PERSONAL_DOMAINS].some((known) => d.endsWith(`.${known}`));
}

export type EmailCheck = { ok: boolean; message: string | null; domain: string };

export function checkFounderEmail(email: string): EmailCheck {
  const trimmed = email.trim();
  const domain = emailDomain(trimmed);
  if (!trimmed) return { ok: false, message: "Enter your work email address.", domain: "" };
  if (!isValidEmail(trimmed))
    return { ok: false, message: "That does not look like an email address.", domain };
  if (isPersonalEmailDomain(domain))
    return {
      ok: false,
      message: `Use your company email, not a personal ${domain} address.`,
      domain,
    };
  return { ok: true, message: null, domain };
}

export function checkEmail(email: string): EmailCheck {
  const trimmed = email.trim();
  const domain = emailDomain(trimmed);
  if (!trimmed) return { ok: false, message: "Enter your email address.", domain: "" };
  if (!isValidEmail(trimmed))
    return { ok: false, message: "That does not look like an email address.", domain };
  return { ok: true, message: null, domain };
}

export const COUNTRY_OPTIONS = [
  "Nigeria",
  "Ghana",
  "Kenya",
  "South Africa",
  "United Kingdom",
  "United States",
  "Canada",
  "India",
  "Singapore",
  "Germany",
  "Netherlands",
  "United Arab Emirates",
];

export const SECTORS = [
  "Fintech",
  "Healthtech",
  "SaaS / B2B",
  "Climate",
  "AI Infrastructure",
  "Marketplace",
  "Consumer",
  "Deeptech",
];

export const STAGES = ["Idea", "Pre-seed", "Seed", "Series A", "Series B+", "Growth"];

export const STAGE_TO_WIRE: Record<string, string> = {
  Idea: "idea",
  "Pre-seed": "pre_seed",
  Seed: "seed",
  "Series A": "series_a",
  "Series B+": "series_b_plus",
  Growth: "growth",
};

export const WIRE_TO_STAGE: Record<string, string> = Object.fromEntries(
  Object.entries(STAGE_TO_WIRE).map(([label, wire]) => [wire, label]),
);

export const COUNTRY_TO_CODE: Record<string, { code: string; currency: string }> = {
  Nigeria: { code: "NG", currency: "NGN" },
  Ghana: { code: "GH", currency: "GHS" },
  Kenya: { code: "KE", currency: "KES" },
  "South Africa": { code: "ZA", currency: "ZAR" },
  "United Kingdom": { code: "GB", currency: "GBP" },
  "United States": { code: "US", currency: "USD" },
  Canada: { code: "CA", currency: "CAD" },
  India: { code: "IN", currency: "INR" },
  Singapore: { code: "SG", currency: "SGD" },
  Germany: { code: "DE", currency: "EUR" },
  Netherlands: { code: "NL", currency: "EUR" },
  "United Arab Emirates": { code: "AE", currency: "AED" },
};

export const CODE_TO_COUNTRY: Record<string, string> = Object.fromEntries(
  Object.entries(COUNTRY_TO_CODE).map(([name, row]) => [row.code, name]),
);
