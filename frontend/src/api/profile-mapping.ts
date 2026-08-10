import {
  COST_TRENDS,
  type CostTrend,
  type FounderProfile,
  type RevModel,
  type YesNo,
} from '@/domain/types';

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
  investor_visible?: boolean;
  published_at?: string | null;
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
const COUNTRIES: { names: string[]; code: string; currency: string; label: string }[] = [
  { names: ['nigeria', 'ng'], code: 'NG', currency: 'NGN', label: 'Nigeria' },
  { names: ['ghana', 'gh'], code: 'GH', currency: 'GHS', label: 'Ghana' },
  { names: ['kenya', 'ke'], code: 'KE', currency: 'KES', label: 'Kenya' },
  { names: ['south africa', 'za'], code: 'ZA', currency: 'ZAR', label: 'South Africa' },
  {
    names: ['united kingdom', 'uk', 'england', 'scotland', 'wales', 'gb'],
    code: 'GB',
    currency: 'GBP',
    label: 'United Kingdom',
  },
  { names: ['united states', 'usa', 'us', 'america'], code: 'US', currency: 'USD', label: 'United States' },
  { names: ['canada', 'ca'], code: 'CA', currency: 'CAD', label: 'Canada' },
  { names: ['india', 'in'], code: 'IN', currency: 'INR', label: 'India' },
  { names: ['singapore', 'sg'], code: 'SG', currency: 'SGD', label: 'Singapore' },
  { names: ['germany', 'de'], code: 'DE', currency: 'EUR', label: 'Germany' },
  { names: ['netherlands', 'nl'], code: 'NL', currency: 'EUR', label: 'Netherlands' },
  {
    names: ['united arab emirates', 'uae', 'ae', 'dubai'],
    code: 'AE',
    currency: 'AED',
    label: 'United Arab Emirates',
  },
];

/** Labels for the onboarding country picker (canonical names that resolve). */
export const COUNTRY_OPTIONS = COUNTRIES.map((c) => c.label);

/** Currency for a resolved country label, or null when unknown. */
export function currencyForCountryLabel(label: string): string | null {
  return resolveCountry(label)?.currency ?? null;
}

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
  // Deliberately empty. Every question the form asks now has somewhere to go
  // (`docs/INTAKE.md`): the five that did not were either replaced by the raw
  // inputs the server actually wants, or removed because they asked the
  // founder for a figure the platform computes itself.
  //
  // The machinery stays because the two field sets drift. `fields.py` is
  // flagged provisional in the backend's own task list, so the next change
  // there could orphan a question again -- and a founder typing an answer that
  // is silently discarded is the failure this list exists to prevent.
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

  // Free text, stored as given.
  if (profile.description.trim()) fields.description = founderField(profile.description.trim());
  if (profile.businessModel.trim()) fields.business_model = founderField(profile.businessModel.trim());
  if (profile.website.trim()) fields.website = founderField(profile.website.trim());
  if (profile.keyPersonDependency.trim()) {
    fields.key_person_dependency = founderField(profile.keyPersonDependency.trim());
  }

  // The narrative answers. All optional to the server, and all worth more to
  // the audit than another number: they are what it cites when it explains a
  // verdict rather than just scoring one.
  for (const [key, source] of [
    ['market_size_note', profile.marketSize],
    ['competition_note', profile.competition],
    ['growth_constraint', profile.growthConstraint],
    ['use_of_funds', profile.useOfFunds],
    ['founder_experience', profile.founderExperience],
    ['cap_table_summary', profile.capTable],
    ['delivery_cost_trend', profile.deliveryCostTrend],
    ['legal_name', profile.legalName],
    ['registration_number', profile.registrationNumber],
    ['registrar', profile.registrar],
    ['regulatory_licences', profile.regulatoryLicences],
  ] as const) {
    if (source.trim()) fields[key] = founderField(source.trim());
  }

  const incorporated = num(profile.incorporationYear);
  if (incorporated !== null) fields.incorporation_year = founderField(Math.round(incorporated));

  const year = num(profile.year);
  if (year !== null) fields.founded_year = founderField(Math.round(year));

  // Whole numbers of people and customers.
  for (const [key, source] of [
    ['founder_count', profile.founders],
    ['founders_full_time', profile.foundersFullTime],
    ['team_size', profile.teamSize],
    ['active_customers', profile.customers],
    ['monthly_active_users', profile.activeUsers],
    ['pilot_or_lou_count', profile.pilots],
  ] as const) {
    const value = num(source);
    if (value !== null) fields[key] = founderField(Math.round(value));
  }

  const churn = num(profile.churn);
  if (churn !== null) fields.monthly_churn_percent = founderField(churn);

  const concentration = num(profile.customerConcentration);
  if (concentration !== null) {
    fields.largest_customer_revenue_share_percent = founderField(concentration);
  }

  // Yes/No maps to a real boolean; unanswered stays absent rather than false,
  // because "we did not ask yet" and "no" are different findings.
  if (profile.ipOwned) fields.ip_owned = founderField(profile.ipOwned === 'Yes');
  if (profile.contractsTransferable) {
    fields.contracts_transferable = founderField(profile.contractsTransferable === 'Yes');
  }

  // Money needs a currency to be meaningful in minor units, and the currency
  // comes from the country. Without one, sending an integer would be storing a
  // number whose unit nobody knows.
  const currency = country?.currency;
  if (currency) {
    const revenue = monthlyRevenue(profile.revenue, profile.revModel);
    if (revenue !== null) {
      fields.monthly_revenue_minor = founderField(toMinorUnits(revenue, currency));
    }
    // Everything else is already a plain monthly or absolute amount.
    for (const [key, source] of [
      ['customer_acquisition_cost_minor', profile.cac],
      ['monthly_costs_minor', profile.costs],
      ['cost_of_revenue_minor', profile.costOfRevenue],
      ['cash_on_hand_minor', profile.cash],
      ['total_raised_minor', profile.totalRaised],
      ['current_raise_target_minor', profile.raiseTarget],
      ['average_revenue_per_customer_minor', profile.arpu],
      ['monthly_marketing_spend_minor', profile.marketingSpend],
    ] as const) {
      const value = num(source);
      if (value !== null) fields[key] = founderField(toMinorUnits(value, currency));
    }
  } else {
    for (const field of [
      'revenue',
      'cac',
      'costs',
      'costOfRevenue',
      'cash',
      'totalRaised',
      'raiseTarget',
      'arpu',
      'marketingSpend',
    ] as const) {
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

function fieldText(fields: Record<string, WireField>, name: string): string {
  const value = fields[name]?.value;
  return typeof value === 'string' ? value : '';
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

  const foundedYear = fieldNumber(fields, 'founded_year');
  const country = COUNTRIES.find((c) => c.code === response.country);

  /** A stored money amount, back in the units a person would type. */
  const money = (name: string): string => {
    const minor = fieldNumber(fields, name);
    return minor === null ? '' : String(fromMinorUnits(minor, currency));
  };

  /** A stored whole number. */
  const count = (name: string): string => {
    const value = fieldNumber(fields, name);
    return value === null ? '' : String(value);
  };

  /** A stored boolean, back as the form's tri-state. Absent stays unanswered. */
  const yesNo = (name: string): YesNo => {
    const raw = fields[name];
    if (!raw || typeof raw.value !== 'boolean') return '';
    return raw.value ? 'Yes' : 'No';
  };

  return {
    company: response.name ?? '',
    sector: response.sector ?? '',
    // The city is not stored, so this comes back as the country alone.
    location: country ? country.label : '',
    year: foundedYear === null ? '' : String(foundedYear),
    stage: response.stage ? (WIRE_TO_STAGE[response.stage] ?? '') : '',
    description: fieldText(fields, 'description'),
    businessModel: fieldText(fields, 'business_model'),
    website: fieldText(fields, 'website'),

    legalName: fieldText(fields, 'legal_name'),
    registrationNumber: fieldText(fields, 'registration_number'),
    registrar: fieldText(fields, 'registrar'),
    incorporationYear: count('incorporation_year'),
    regulatoryLicences: fieldText(fields, 'regulatory_licences'),

    marketSize: fieldText(fields, 'market_size_note'),
    competition: fieldText(fields, 'competition_note'),
    growthConstraint: fieldText(fields, 'growth_constraint'),
    useOfFunds: fieldText(fields, 'use_of_funds'),

    // Always read back as monthly: that is how it is stored, whatever unit the
    // founder originally typed it in.
    revModel: 'MRR',
    revenue: money('monthly_revenue_minor'),
    costs: money('monthly_costs_minor'),
    costOfRevenue: money('cost_of_revenue_minor'),
    cash: money('cash_on_hand_minor'),
    totalRaised: money('total_raised_minor'),
    raiseTarget: money('current_raise_target_minor'),
    marketingSpend: money('monthly_marketing_spend_minor'),

    customers: count('active_customers'),
    arpu: money('average_revenue_per_customer_minor'),
    churn: count('monthly_churn_percent'),
    activeUsers: count('monthly_active_users'),
    pilots: count('pilot_or_lou_count'),
    customerConcentration: count('largest_customer_revenue_share_percent'),
    // Only adopted when it is one of the three the form offers; anything else
    // came from somewhere other than this app and would not fit the control.
    deliveryCostTrend: (COST_TRENDS as readonly string[]).includes(
      fieldText(fields, 'delivery_cost_trend'),
    )
      ? (fieldText(fields, 'delivery_cost_trend') as CostTrend)
      : '',
    cac: money('customer_acquisition_cost_minor'),

    founders: count('founder_count'),
    foundersFullTime: count('founders_full_time'),
    teamSize: count('team_size'),
    ipOwned: yesNo('ip_owned'),
    contractsTransferable: yesNo('contracts_transferable'),
    keyPersonDependency: fieldText(fields, 'key_person_dependency'),
    founderExperience: fieldText(fields, 'founder_experience'),
    capTable: fieldText(fields, 'cap_table_summary'),

    deck: '',
  };
}
