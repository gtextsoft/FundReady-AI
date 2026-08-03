import type { FounderProfile, RevModel } from '@/domain/types';

/**
 * Translating the onboarding form into the server's Startup Profile.
 *
 * These two shapes were designed independently — the form came from the design
 * prototype, the field list from `modules/intake/fields.py` — and they do not
 * line up. Six of the form's answers have nowhere to go on the server today.
 *
 * **The mismatch is reported, never swallowed.** `toWireProfile` returns the
 * unmapped answers alongside the payload so a caller can say what was not
 * saved. Dropping them silently is the worse failure: the founder types a
 * number, the screen accepts it, and it is gone — and later, when the audit
 * does not mention it, nothing anywhere explains why.
 *
 * Nothing here derives a value the founder did not enter. Gross margin plus
 * revenue would *yield* `cost_of_revenue_minor`, and it is tempting, but a
 * figure the client computed and labelled `founder` is a fabricated input to an
 * audit that has to cite its evidence. If those derivations are wanted they
 * belong on the server, marked as derived.
 *
 * `fields.py` is flagged **provisional** in the backend's own task list pending
 * the missing spec, so expect this file to move with it.
 */

/** The server's `Stage` enum (`modules/intake/fields.py`). */
export type ServerStage = 'idea' | 'pre_seed' | 'seed' | 'series_a' | 'series_b_plus' | 'growth';

/** One field as the server stores it, with its provenance. */
export type WireField = {
  value: string | number | boolean | null;
  source: 'founder' | 'document' | 'inferred';
  confidence?: number | null;
  document_id?: string | null;
};

export type WireProfile = {
  name?: string;
  sector?: string;
  stage?: ServerStage;
  country?: string;
  currency?: string;
  fields?: Record<string, WireField>;
};

/**
 * The full profile as `GET /v1/startups/me` returns it.
 *
 * Declared standalone rather than as `WireProfile & {…}`: on the way out a
 * field is *omitted* when it has no value, on the way back it is present and
 * `null`. Intersecting the two collapses `string | undefined` with
 * `string | null` down to `string`, which would quietly assert that the server
 * never returns a null — and it returns them constantly.
 */
export type WireProfileResponse = {
  id: string;
  owner_id: string;
  name: string | null;
  sector: string | null;
  stage: ServerStage | null;
  country: string | null;
  currency: string | null;
  fields: Record<string, WireField>;
  missing_fields: string[];
  created_at: string;
  updated_at: string;
};

/** An answer the server has no home for, and why. */
export type UnmappedAnswer = {
  field: keyof FounderProfile;
  value: string;
  reason: string;
};

export type ProfileMapping = {
  wire: WireProfile;
  unmapped: UnmappedAnswer[];
};

// ── stage ───────────────────────────────────────────────────

const STAGE_TO_WIRE: Record<string, ServerStage> = {
  'Pre-seed': 'pre_seed',
  Seed: 'seed',
  'Series A': 'series_a',
  Growth: 'growth',
};

const WIRE_TO_STAGE: Record<ServerStage, string> = {
  idea: 'Pre-seed',
  pre_seed: 'Pre-seed',
  seed: 'Seed',
  series_a: 'Series A',
  series_b_plus: 'Series A',
  growth: 'Growth',
};

// ── country and currency ────────────────────────────────────

/**
 * The markets the app names in `founder/verify.tsx`, plus their currency.
 *
 * The server wants ISO 3166-1 alpha-2 and ISO 4217; the form asks for a free
 * text "Lagos, Nigeria". An unrecognised location is reported unmapped rather
 * than guessed — a wrong country silently selects the wrong benchmark set, and
 * the founder is then scored against the wrong market with no sign of it.
 */
const COUNTRIES: { names: string[]; code: string; currency: string }[] = [
  { names: ['nigeria', 'ng'], code: 'NG', currency: 'NGN' },
  { names: ['ghana', 'gh'], code: 'GH', currency: 'GHS' },
  { names: ['kenya', 'ke'], code: 'KE', currency: 'KES' },
  { names: ['south africa', 'za'], code: 'ZA', currency: 'ZAR' },
  {
    names: ['united kingdom', 'uk', 'england', 'scotland', 'wales', 'gb'],
    code: 'GB',
    currency: 'GBP',
  },
  { names: ['united states', 'usa', 'us', 'america'], code: 'US', currency: 'USD' },
  { names: ['canada', 'ca'], code: 'CA', currency: 'CAD' },
  { names: ['india', 'in'], code: 'IN', currency: 'INR' },
  { names: ['singapore', 'sg'], code: 'SG', currency: 'SGD' },
  { names: ['germany', 'de'], code: 'DE', currency: 'EUR' },
  { names: ['netherlands', 'nl'], code: 'NL', currency: 'EUR' },
  { names: ['united arab emirates', 'uae', 'ae', 'dubai'], code: 'AE', currency: 'AED' },
];

/** Resolves "Lagos, Nigeria" to `NG`. Null when nothing matches. */
export function resolveCountry(location: string): { code: string; currency: string } | null {
  const text = location.trim().toLowerCase();
  if (!text) return null;
  // Compare against the comma-separated parts so a city name cannot match a
  // country by accident ("Indiana" must not resolve to India).
  const parts = text.split(',').map((p) => p.trim());
  for (const country of COUNTRIES) {
    if (parts.some((part) => country.names.includes(part))) {
      return { code: country.code, currency: country.currency };
    }
  }
  return null;
}

// ── money ───────────────────────────────────────────────────

/**
 * Currencies with no minor unit. None of them are in `COUNTRIES` today, but
 * multiplying a yen figure by 100 would overstate revenue by 100x, and that is
 * too quiet a way to fail to leave to chance.
 */
const ZERO_DECIMAL = new Set(['JPY', 'KRW', 'VND', 'CLP', 'ISK', 'XAF', 'XOF', 'UGX', 'RWF']);

/** Whole currency units to the integer minor units the server stores. */
export function toMinorUnits(amount: number, currency: string): number {
  return ZERO_DECIMAL.has(currency) ? Math.round(amount) : Math.round(amount * 100);
}

export function fromMinorUnits(minor: number, currency: string): number {
  return ZERO_DECIMAL.has(currency) ? minor : minor / 100;
}

/** A form string as a number, or null when it is blank or not a number. */
function num(value: string): number | null {
  const trimmed = value.trim().replace(/[, ]/g, '');
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Monthly revenue, whatever the founder chose to report. */
export function monthlyRevenue(revenue: string, model: RevModel): number | null {
  const value = num(revenue);
  if (value === null) return null;
  return model === 'ARR' ? value / 12 : value;
}

// ── form → server ───────────────────────────────────────────

const founderField = (value: string | number | boolean): WireField => ({
  value,
  source: 'founder',
});

/**
 * Answers the server's field list has no place for.
 *
 * Listed here rather than inline so the set is countable and testable — the
 * moment `fields.py` grows one of these, a test fails and points at the line
 * to delete.
 */
const NO_SERVER_FIELD: { field: keyof FounderProfile; reason: string }[] = [
  { field: 'growth', reason: 'The profile has no growth field — it needs monthly history, not one number.' },
  { field: 'tam', reason: 'The profile has no market-size field.' },
  { field: 'margin', reason: 'The profile stores cost of revenue, not a margin percentage.' },
  { field: 'ltv', reason: 'Lifetime value is computed from churn and revenue, not stored.' },
  { field: 'technical', reason: 'The profile has no technical-founder field.' },
];

/**
 * Converts the onboarding form into a create/update payload.
 *
 * Blank answers are omitted rather than sent as null: the server merges
 * `fields` by name, so an omitted key leaves what is already there alone, and
 * an empty form must never wipe values that document extraction filled in.
 */
export function toWireProfile(profile: FounderProfile): ProfileMapping {
  const wire: WireProfile = {};
  const fields: Record<string, WireField> = {};
  const unmapped: UnmappedAnswer[] = [];

  if (profile.company.trim()) wire.name = profile.company.trim();
  if (profile.sector.trim()) wire.sector = profile.sector.trim();

  const country = resolveCountry(profile.location);
  if (country) {
    wire.country = country.code;
    wire.currency = country.currency;
  } else if (profile.location.trim()) {
    unmapped.push({
      field: 'location',
      value: profile.location,
      reason: 'Could not tell which country this is, and a guess would pick the wrong benchmarks.',
    });
  }

  if (profile.stage) {
    const stage = STAGE_TO_WIRE[profile.stage];
    if (stage) {
      wire.stage = stage;
    } else {
      // 'Bootstrapped' is a funding *posture*, not a stage, and the server's
      // enum has no room for it.
      unmapped.push({
        field: 'stage',
        value: profile.stage,
        reason: `"${profile.stage}" is not one of the stages the profile accepts.`,
      });
    }
  }

  const year = num(profile.year);
  if (year !== null) fields.founded_year = founderField(Math.round(year));

  const founders = num(profile.founders);
  if (founders !== null) fields.founder_count = founderField(Math.round(founders));

  // Money needs a currency to be meaningful in minor units, and the currency
  // comes from the country. Without one, sending an integer would be storing a
  // number whose unit nobody knows.
  const currency = country?.currency;
  if (currency) {
    const revenue = monthlyRevenue(profile.revenue, profile.revModel);
    if (revenue !== null) {
      fields.monthly_revenue_minor = founderField(toMinorUnits(revenue, currency));
    }
    const cac = num(profile.cac);
    if (cac !== null) {
      fields.customer_acquisition_cost_minor = founderField(toMinorUnits(cac, currency));
    }
  } else {
    for (const field of ['revenue', 'cac'] as const) {
      if (profile[field].trim()) {
        unmapped.push({
          field,
          value: profile[field],
          reason: 'Money cannot be stored without knowing the currency, which comes from the country.',
        });
      }
    }
  }

  for (const { field, reason } of NO_SERVER_FIELD) {
    const value = profile[field];
    if (typeof value === 'string' && value.trim()) unmapped.push({ field, value, reason });
  }

  if (Object.keys(fields).length > 0) wire.fields = fields;
  return { wire, unmapped };
}

// ── server → form ───────────────────────────────────────────

function fieldNumber(fields: Record<string, WireField>, name: string): number | null {
  const value = fields[name]?.value;
  return typeof value === 'number' ? value : null;
}

/**
 * Rebuilds the form from a stored profile.
 *
 * Round-tripping is deliberately lossy in the same places the mapping above
 * is: what the server never received, it cannot give back. Revenue always
 * returns as MRR, because the monthly figure is what was stored — an ARR
 * entry of 120,000 comes back as 10,000/month, which is the same fact stated
 * the way the server holds it.
 */
export function fromWireProfile(response: WireProfileResponse): FounderProfile {
  const fields = response.fields ?? {};
  const currency = response.currency ?? 'USD';

  const revenueMinor = fieldNumber(fields, 'monthly_revenue_minor');
  const cacMinor = fieldNumber(fields, 'customer_acquisition_cost_minor');
  const foundedYear = fieldNumber(fields, 'founded_year');
  const founderCount = fieldNumber(fields, 'founder_count');

  const country = COUNTRIES.find((c) => c.code === response.country);

  return {
    company: response.name ?? '',
    sector: response.sector ?? '',
    // The city is not stored, so this comes back as the country alone.
    location: country ? country.names[0].replace(/\b\w/g, (m) => m.toUpperCase()) : '',
    year: foundedYear === null ? '' : String(foundedYear),
    stage: response.stage ? (WIRE_TO_STAGE[response.stage] ?? '') : '',
    revModel: 'MRR',
    revenue: revenueMinor === null ? '' : String(fromMinorUnits(revenueMinor, currency)),
    growth: '',
    tam: '',
    margin: '',
    cac: cacMinor === null ? '' : String(fromMinorUnits(cacMinor, currency)),
    ltv: '',
    founders: founderCount === null ? '' : String(founderCount),
    technical: '',
    deck: '',
  };
}
