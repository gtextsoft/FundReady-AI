/**
 * The onboarding form ↔ Startup Profile mapping.
 *
 * Two things are being defended here. **Money must not change by 100x** — the
 * server stores integer minor units and the form collects whole ones — and
 * **nothing may be dropped in silence**: every answer that has no server field
 * must come back in `unmapped` so a screen can say so.
 */

import {
  fromMinorUnits,
  fromWireProfile,
  monthlyRevenue,
  resolveCountry,
  toMinorUnits,
  toWireProfile,
  type WireProfileResponse,
} from '@/api/profile-mapping';
import { EMPTY_PROFILE, type FounderProfile } from '@/domain/types';

const form = (overrides: Partial<FounderProfile> = {}): FounderProfile => ({
  ...EMPTY_PROFILE,
  ...overrides,
});

describe('resolveCountry', () => {
  it('reads the country out of "City, Country"', () => {
    expect(resolveCountry('Lagos, Nigeria')).toEqual({ code: 'NG', currency: 'NGN' });
    expect(resolveCountry('London, United Kingdom')).toEqual({ code: 'GB', currency: 'GBP' });
  });

  it('accepts the country on its own, in any case', () => {
    expect(resolveCountry('  KENYA ')?.code).toBe('KE');
  });

  it('does not match a country inside a longer word', () => {
    // "Indianapolis, United States" must be US, never IN.
    expect(resolveCountry('Indianapolis, United States')?.code).toBe('US');
    expect(resolveCountry('Indiana')).toBeNull();
  });

  it('returns null rather than guessing', () => {
    expect(resolveCountry('Atlantis')).toBeNull();
    expect(resolveCountry('')).toBeNull();
  });
});

describe('minor units', () => {
  it('converts whole units to minor and back', () => {
    expect(toMinorUnits(48000, 'NGN')).toBe(4_800_000);
    expect(fromMinorUnits(4_800_000, 'NGN')).toBe(48000);
  });

  it('rounds rather than storing a fractional minor unit', () => {
    expect(toMinorUnits(10.005, 'USD')).toBe(1001);
  });

  it('leaves zero-decimal currencies alone', () => {
    // Multiplying yen by 100 would report revenue 100x too high.
    expect(toMinorUnits(48000, 'JPY')).toBe(48000);
    expect(fromMinorUnits(48000, 'JPY')).toBe(48000);
  });
});

describe('monthlyRevenue', () => {
  it('takes MRR as entered', () => {
    expect(monthlyRevenue('48000', 'MRR')).toBe(48000);
  });

  it('divides ARR by twelve', () => {
    expect(monthlyRevenue('120000', 'ARR')).toBe(10000);
  });

  it('tolerates the separators people type', () => {
    expect(monthlyRevenue('48,000', 'MRR')).toBe(48000);
  });

  it('is null for blank or nonsense, never zero', () => {
    // Zero would be scored as a real "no revenue" rather than "not answered".
    expect(monthlyRevenue('', 'MRR')).toBeNull();
    expect(monthlyRevenue('soon', 'MRR')).toBeNull();
  });
});

describe('toWireProfile', () => {
  it('maps the answers that have a home', () => {
    const { wire } = toWireProfile(
      form({
        company: ' Northwind Labs ',
        sector: 'Fintech',
        location: 'Lagos, Nigeria',
        year: '2023',
        stage: 'Seed',
        revenue: '48000',
        revModel: 'MRR',
        cac: '320',
        founders: '2',
      }),
    );

    expect(wire).toEqual({
      name: 'Northwind Labs',
      sector: 'Fintech',
      stage: 'seed',
      country: 'NG',
      currency: 'NGN',
      fields: {
        founded_year: { value: 2023, source: 'founder' },
        founder_count: { value: 2, source: 'founder' },
        monthly_revenue_minor: { value: 4_800_000, source: 'founder' },
        customer_acquisition_cost_minor: { value: 32_000, source: 'founder' },
      },
    });
  });

  it('omits blank answers instead of sending nulls', () => {
    // The server merges `fields` by name, so a null would wipe a value that
    // document extraction had filled in.
    const { wire } = toWireProfile(form({ company: 'Northwind Labs' }));
    expect(wire).toEqual({ name: 'Northwind Labs' });
    expect(wire.fields).toBeUndefined();
  });

  it('reports every answer the server has no field for', () => {
    // The form no longer asks anything the profile cannot store, so the only
    // way to land here is an unrecognised location or stage. Both are answers
    // the founder gave that we decline to guess at.
    const { unmapped } = toWireProfile(
      form({
        location: 'Somewhere Unmappable',
        stage: 'Bootstrapped',
      }),
    );

    expect(unmapped.map((u) => u.field).sort()).toEqual(['location', 'stage']);
    for (const answer of unmapped) {
      expect(answer.reason.length).toBeGreaterThan(20);
    }
  });

  it('asks nothing the profile cannot store', () => {
    // The guard against the form drifting ahead of `fields.py` again. A fully
    // answered form, in a country we know, must produce no unmapped answers at
    // all — if this fails, a question was added with nowhere to put it.
    const { unmapped } = toWireProfile({
      ...form({}),
      company: 'Northwind Labs',
      sector: 'Fintech',
      location: 'Lagos, Nigeria',
      year: '2023',
      stage: 'Seed',
      description: 'Reconciliation software for payment processors.',
      businessModel: 'Monthly subscription per processor.',
      website: 'northwindlabs.com',
      revenue: '48000',
      costs: '62000',
      costOfRevenue: '9000',
      cash: '410000',
      totalRaised: '150000',
      raiseTarget: '500000',
      customers: '180',
      arpu: '270',
      churn: '3',
      cac: '320',
      founders: '2',
      foundersFullTime: '2',
      teamSize: '7',
      ipOwned: 'Yes',
      contractsTransferable: 'Yes',
      keyPersonDependency: 'Enterprise pricing decisions.',
      // Registration, collected on the verification screen.
      legalName: 'Northwind Labs Limited',
      registrationNumber: 'RC 1234567',
      registrar: 'CAC',
      incorporationYear: '2023',
      regulatoryLicences: 'None needed for reconciliation software.',
      // Market and plan.
      marketSize: 'About 400 processors already on our rails.',
      competition: 'Spreadsheets, and one incumbent add-on.',
      growthConstraint: 'Manual integration caps us at six onboardings a month.',
      useOfFunds: 'Two integration engineers.',
      // Operations, traction and ownership.
      founderExperience: 'Led payments integrations at Interswitch for four years.',
      deliveryCostTrend: 'Falling',
      capTable: 'Founders 70%, angels 12%, ESOP 18%',
      marketingSpend: '40000',
      activeUsers: '2400',
      pilots: '3',
      customerConcentration: '35',
    });

    expect(unmapped).toEqual([]);
  });

  it('reports an unrecognised location rather than picking a country', () => {
    // A wrong country silently selects the wrong benchmark set.
    const { wire, unmapped } = toWireProfile(form({ location: 'Atlantis' }));
    expect(wire.country).toBeUndefined();
    expect(unmapped.map((u) => u.field)).toContain('location');
  });

  it('refuses to store money when the currency is unknown', () => {
    // An integer with no known unit is worse than no value at all.
    const { wire, unmapped } = toWireProfile(
      form({ location: 'Atlantis', revenue: '48000', cac: '320' }),
    );
    expect(wire.fields).toBeUndefined();
    expect(unmapped.map((u) => u.field)).toEqual(
      expect.arrayContaining(['revenue', 'cac']),
    );
  });

  it('reports Bootstrapped, which is not one of the server stages', () => {
    const { wire, unmapped } = toWireProfile(form({ stage: 'Bootstrapped' }));
    expect(wire.stage).toBeUndefined();
    expect(unmapped.find((u) => u.field === 'stage')?.value).toBe('Bootstrapped');
  });

  it('sends cost of revenue only when the founder gave one', () => {
    // The client must never infer it. Revenue x (1 - margin) is arithmetic it
    // could do, but a figure nobody entered must not reach the audit labelled
    // `founder` — the form asks for the cost directly for exactly this reason.
    const { wire } = toWireProfile(form({ location: 'Lagos, Nigeria', revenue: '48000' }));
    expect(wire.fields?.cost_of_revenue_minor).toBeUndefined();

    const given = toWireProfile(
      form({ location: 'Lagos, Nigeria', revenue: '48000', costOfRevenue: '9000' }),
    );
    expect(given.wire.fields?.cost_of_revenue_minor?.value).toBe(900000);
  });

  it('marks everything it does send as founder-reported', () => {
    const { wire } = toWireProfile(form({ location: 'Lagos, Nigeria', revenue: '48000' }));
    for (const field of Object.values(wire.fields ?? {})) {
      expect(field.source).toBe('founder');
    }
  });
});

describe('fromWireProfile', () => {
  const stored: WireProfileResponse = {
    id: 'profile-1',
    owner_id: 'user-1',
    name: 'Northwind Labs',
    sector: 'Fintech',
    stage: 'seed',
    country: 'NG',
    currency: 'NGN',
    fields: {
      founded_year: { value: 2023, source: 'founder' },
      founder_count: { value: 2, source: 'founder' },
      monthly_revenue_minor: { value: 4_800_000, source: 'founder' },
      customer_acquisition_cost_minor: { value: 32_000, source: 'document' },
    },
    missing_fields: ['business_model'],
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-02T00:00:00Z',
  };

  it('rebuilds the form from what the server holds', () => {
    const profile = fromWireProfile(stored);
    expect(profile).toMatchObject({
      company: 'Northwind Labs',
      sector: 'Fintech',
      stage: 'Seed',
      location: 'Nigeria',
      year: '2023',
      revenue: '48000',
      revModel: 'MRR',
      cac: '320',
      founders: '2',
    });
  });

  it('round-trips the mappable answers unchanged', () => {
    const original = form({
      company: 'Northwind Labs',
      sector: 'Fintech',
      location: 'Nigeria',
      year: '2023',
      stage: 'Seed',
      revenue: '48000',
      founders: '2',
    });
    const { wire } = toWireProfile(original);
    const back = fromWireProfile({ ...stored, ...wire, fields: wire.fields ?? {} });

    expect(back.company).toBe(original.company);
    expect(back.revenue).toBe(original.revenue);
    expect(back.stage).toBe(original.stage);
    expect(back.location).toBe(original.location);
  });

  it('returns blanks for what was never storable', () => {
    const profile = fromWireProfile(stored);
    // The deck is a document, not a profile field, so it never round-trips.
    expect(profile.deck).toBe('');
    // Absent booleans stay unanswered rather than becoming "No": not asked and
    // answered no are different findings.
    expect(profile.ipOwned).toBe('');
    expect(profile.contractsTransferable).toBe('');
  });

  it('survives a profile with nothing in it', () => {
    const empty: WireProfileResponse = {
      ...stored,
      name: null,
      sector: null,
      stage: null,
      country: null,
      currency: null,
      fields: {},
    };
    expect(fromWireProfile(empty)).toEqual(EMPTY_PROFILE);
  });
});


describe('the fields added in August 2026', () => {
  const answered = {
    ...form({}),
    location: 'Lagos, Nigeria',
    legalName: 'Northwind Labs Limited',
    registrationNumber: 'RC 1234567',
    registrar: 'CAC',
    incorporationYear: '2023',
    regulatoryLicences: 'None needed.',
    marketSize: 'About 400 processors.',
    competition: 'Spreadsheets.',
    growthConstraint: 'Manual integration.',
    useOfFunds: 'Two engineers.',
    founderExperience: 'Four years at Interswitch.',
    deliveryCostTrend: 'Falling' as const,
    capTable: 'Founders 70%.',
    marketingSpend: '40000',
    activeUsers: '2400',
    pilots: '3',
    customerConcentration: '35',
  };

  it('sends every one of them under the name the server uses', () => {
    const { wire, unmapped } = toWireProfile(answered);
    const f = wire.fields ?? {};

    expect(f.legal_name?.value).toBe('Northwind Labs Limited');
    expect(f.registration_number?.value).toBe('RC 1234567');
    expect(f.registrar?.value).toBe('CAC');
    expect(f.incorporation_year?.value).toBe(2023);
    expect(f.regulatory_licences?.value).toBe('None needed.');
    expect(f.market_size_note?.value).toBe('About 400 processors.');
    expect(f.competition_note?.value).toBe('Spreadsheets.');
    expect(f.growth_constraint?.value).toBe('Manual integration.');
    expect(f.use_of_funds?.value).toBe('Two engineers.');
    expect(f.founder_experience?.value).toBe('Four years at Interswitch.');
    expect(f.delivery_cost_trend?.value).toBe('Falling');
    expect(f.cap_table_summary?.value).toBe('Founders 70%.');
    expect(f.monthly_active_users?.value).toBe(2400);
    expect(f.pilot_or_lou_count?.value).toBe(3);
    expect(f.largest_customer_revenue_share_percent?.value).toBe(35);
    // Money, so minor units — 40,000 naira is 4,000,000 kobo.
    expect(f.monthly_marketing_spend_minor?.value).toBe(4_000_000);

    expect(unmapped).toEqual([]);
  });

  it('round-trips them back into the form', () => {
    const { wire } = toWireProfile(answered);
    const back = fromWireProfile({
      id: 'p1',
      owner_id: 'u1',
      name: null,
      sector: null,
      stage: null,
      country: 'NG',
      currency: 'NGN',
      fields: wire.fields ?? {},
      missing_fields: [],
      created_at: '2026-08-10T00:00:00Z',
      updated_at: '2026-08-10T00:00:00Z',
    });

    expect(back.legalName).toBe(answered.legalName);
    expect(back.incorporationYear).toBe('2023');
    expect(back.marketSize).toBe(answered.marketSize);
    expect(back.useOfFunds).toBe(answered.useOfFunds);
    expect(back.deliveryCostTrend).toBe('Falling');
    expect(back.marketingSpend).toBe('40000');
    expect(back.pilots).toBe('3');
    expect(back.customerConcentration).toBe('35');
  });

  it('refuses a cost trend that is not one of the three offered', () => {
    // Anything else came from outside this app and would not fit the control,
    // so it is dropped rather than shown as a selected option that is not there.
    const back = fromWireProfile({
      id: 'p1',
      owner_id: 'u1',
      name: null,
      sector: null,
      stage: null,
      country: 'NG',
      currency: 'NGN',
      fields: { delivery_cost_trend: { value: 'going up a bit', source: 'founder' } },
      missing_fields: [],
      created_at: '2026-08-10T00:00:00Z',
      updated_at: '2026-08-10T00:00:00Z',
    });
    expect(back.deliveryCostTrend).toBe('');
  });
});
