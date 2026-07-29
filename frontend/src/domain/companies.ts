import { C } from '@/theme/tokens';
import type { Company, MatchType, Sector, Stage } from './types';

/**
 * Seed dealflow database, ported from the prototype.
 *
 * Order: name, sector, stage, tagline, location, score, mrr, growth, margin,
 * ltvcac, runway, match, ageDays, founder.
 *
 * This is demo data. Once the backend lists companies for real, delete this
 * file and let `src/api/http.ts` return the same `Company` shape.
 */
type Row = [
  string, Sector, Stage, string, string,
  number, number, number, number, number, number,
  MatchType, number, string,
];

const RAW: Row[] = [
  ['Northwind Ledger', 'Fintech', 'Series A', 'Reconciliation infrastructure for African payment processors', 'Lagos, Nigeria', 86, 142000, 18, 81, 4.2, 19, 'VC', 2, 'Adaeze Nwosu'],
  ['Cadence Health', 'Healthtech', 'Seed', 'Post-discharge monitoring that cuts readmission penalties', 'Boston, MA', 79, 61000, 21, 74, 3.6, 16, 'VC', 5, 'Dr. Ravi Menon'],
  ['Tessellate', 'SaaS / B2B', 'Series A', 'Schema-aware ETL for regulated data teams', 'Berlin, Germany', 83, 198000, 11, 88, 5.1, 22, 'VC', 9, 'Lena Brandt'],
  ['Verdant Grid', 'Climate', 'Growth', 'Demand-response software for industrial cold chains', 'Rotterdam, NL', 77, 340000, 7, 64, 3.9, 26, 'PE', 14, 'Joris Bakker'],
  ['Halcyon Labs', 'AI Infrastructure', 'Seed', 'Inference caching layer that cuts token spend 60%', 'San Francisco, CA', 88, 74000, 34, 91, 6.4, 14, 'VC', 1, 'Priya Raghavan'],
  ['Orlo Markets', 'Marketplace', 'Seed', 'Wholesale produce clearing for mid-market grocers', 'Nairobi, Kenya', 64, 52000, 14, 38, 2.4, 11, 'PE', 7, 'Samuel Otieno'],
  ['Fathom Underwriting', 'Fintech', 'Series A', 'Parametric crop insurance priced off satellite data', 'Ahmedabad, India', 81, 127000, 13, 69, 3.8, 20, 'VC', 6, 'Meera Shah'],
  ['Stillwater Bio', 'Healthtech', 'Pre-seed', 'Assay automation for small diagnostic labs', 'Cambridge, UK', 48, 9000, 6, 52, 1.6, 8, 'VC', 3, 'Tom Reddick'],
  ['Bracket', 'SaaS / B2B', 'Seed', 'Procurement approvals that live inside Slack', 'Austin, TX', 71, 44000, 16, 86, 3.1, 13, 'VC', 4, 'Danielle Cho'],
  ['Corvid Freight', 'Marketplace', 'Growth', 'Backhaul matching for regional trucking fleets', 'Chicago, IL', 74, 410000, 5, 31, 3.4, 29, 'PE', 18, 'Marcus Bell'],
  ['Solvent', 'Fintech', 'Pre-seed', 'Treasury automation for Series A startups', 'Singapore', 56, 14000, 22, 79, 2.2, 9, 'VC', 2, 'Wei Lin Tan'],
  ['Aperture Climate', 'Climate', 'Seed', 'MRV tooling for soil carbon registries', 'Melbourne, AU', 69, 38000, 15, 72, 2.8, 15, 'VC', 8, 'Georgia Pike'],
  ['Loom Kernel', 'AI Infrastructure', 'Series A', 'GPU scheduling for multi-tenant model serving', 'Toronto, CA', 85, 166000, 17, 84, 4.7, 21, 'VC', 5, 'Étienne Roy'],
  ['Meridian Rx', 'Healthtech', 'Growth', 'Specialty pharmacy benefits administration', 'Philadelphia, PA', 72, 520000, 4, 42, 3.2, 31, 'PE', 22, 'Karen Ives'],
  ['Foundry Books', 'SaaS / B2B', 'Pre-seed', 'Close-the-books workflow for multi-entity groups', 'Dublin, IE', 44, 6000, 9, 77, 1.4, 7, 'VC', 1, 'Cian Doyle'],
  ['Palisade Trust', 'Fintech', 'Growth', 'Escrow rails for cross-border M&A', 'Zurich, CH', 80, 610000, 3, 58, 4.0, 34, 'PE', 26, 'Anna Keller'],
  ['Rewire Grid', 'Climate', 'Series A', 'Interconnection queue modelling for developers', 'Denver, CO', 76, 118000, 12, 67, 3.3, 18, 'VC', 10, 'Sofia Marín'],
  ['Kettle', 'Marketplace', 'Seed', 'Liquidation marketplace for restaurant equipment', 'Manchester, UK', 58, 27000, 10, 29, 2.0, 10, 'PE', 12, 'Owen Pritchard'],
  ['Sable Compute', 'AI Infrastructure', 'Pre-seed', 'Bare-metal clusters billed by the second', 'Tallinn, EE', 61, 11000, 28, 55, 1.9, 6, 'VC', 2, 'Kaarel Lepik'],
  ['Ovation Care', 'Healthtech', 'Seed', 'Scheduling and billing for allied health clinics', 'Auckland, NZ', 67, 35000, 13, 73, 2.9, 14, 'VC', 9, 'Hine Walker'],
  ['Quillon', 'SaaS / B2B', 'Growth', 'Contract lifecycle management for insurers', 'Hartford, CT', 73, 470000, 4, 80, 3.5, 28, 'PE', 20, 'Ben Ashford'],
  ['Terrace Energy', 'Climate', 'Pre-seed', 'Heat-pump retrofit financing at point of sale', 'Copenhagen, DK', 52, 8000, 19, 44, 1.7, 7, 'VC', 3, 'Freja Sørensen'],
  ['Bellwether AI', 'AI Infrastructure', 'Seed', 'Eval harnesses for production LLM pipelines', 'Seattle, WA', 82, 58000, 26, 89, 4.4, 15, 'VC', 1, 'Grace Okonkwo'],
  ['Junction Pay', 'Fintech', 'Seed', 'Payouts API for gig platforms in LatAm', 'Mexico City, MX', 75, 49000, 20, 66, 3.0, 12, 'VC', 4, 'Rodrigo Salas'],
];

const CTO_NAMES = ['Ada Cole', 'Nils Berg', 'Yara Haddad', 'Peter Osei', 'Mira Vance'];

function build(row: Row, i: number): Company {
  const [name, sector, stage, tagline, location, score, mrr, growth, margin, ltvcac, runway, match, ageDays, founder] = row;

  // Back-cast six months of revenue from today's MRR at the stated growth rate.
  const base = mrr / Math.pow(1 + growth / 100, 5);
  const trend = [0, 1, 2, 3, 4, 5].map((k) => Math.round(base * Math.pow(1 + growth / 100, k)));

  const memo1 =
    `${name} sells ${tagline.charAt(0).toLowerCase() + tagline.slice(1)}. At $${(mrr / 1000).toFixed(0)}k MRR ` +
    `growing ${growth}% month over month, the company is compounding faster than the ${sector} median at ${stage} ` +
    `stage and does so on ${margin}% gross margin. The thesis rests on ` +
    `${margin >= 70
      ? 'a software cost structure that lets incremental revenue drop through'
      : 'an operationally intensive model that trades margin for defensibility'}, paired with ` +
    `${ltvcac >= 3.5
      ? 'acquisition economics that already pay back inside a year'
      : 'acquisition economics that need another quarter of proof'}.`;

  const memo2 =
    match === 'VC'
      ? `Venture-shaped: ${growth}% monthly compounding, ${margin}% margins and a category where a winner can plausibly reach nine figures of revenue. Capital here buys velocity, not survival.`
      : `Private-equity shaped: ${mrr >= 300000 ? 'meaningful revenue scale' : 'a steady revenue base'} at ${growth}% growth with ${runway} months of runway. The return comes from operating leverage and consolidation, not from a step-change in growth rate.`;

  const fits =
    match === 'VC'
      ? [
          `Top-quartile growth for ${sector} at ${stage}`,
          `LTV:CAC of ${ltvcac.toFixed(1)}:1 clears the institutional 3:1 bar`,
          `${margin}% gross margin supports a capital-efficient scale-up`,
        ]
      : [
          `${runway} months of runway removes financing pressure from the deal`,
          `${margin}% margin with a defined cost line to optimise`,
          'Fragmented competitive set invites a roll-up',
        ];

  const flags = [
    growth < 8
      ? { color: C.red, title: 'Growth below screening floor', body: `${growth}% MoM will read as flat to most growth funds. Confirm whether this is seasonality or saturation.` }
      : { color: C.amb, title: 'Growth durability unproven', body: `${growth}% MoM is strong but measured over two quarters. Model a decay curve before underwriting.` },
    ltvcac < 3
      ? { color: C.red, title: 'Payback period too long', body: `LTV:CAC of ${ltvcac.toFixed(1)}:1 means acquisition spend outruns realised value. Diligence channel mix.` }
      : { color: C.amb, title: 'Concentration risk in acquisition', body: 'Efficient blended CAC, but a single channel likely carries it. Ask for cohort-level attribution.' },
    runway < 12
      ? { color: C.red, title: 'Runway under 12 months', body: `${runway} months forces a raise inside two quarters, which weakens the founder's negotiating position.` }
      : { color: C.amb, title: 'Key-person dependency', body: `${founder} owns the commercial relationships. Succession and equity retention need structuring.` },
  ];

  return {
    id: i + 1,
    name, sector, stage, tagline, location, score, mrr, growth, margin, ltvcac, runway, match, ageDays, founder,
    trend,
    memoDate: '12 Jul 2026',
    responseTime: score >= 80 ? '6 hours' : score >= 65 ? '1 day' : '3 days',
    team: [
      { name: founder, role: 'Co-founder & CEO', note: stage === 'Growth' ? '2nd exit' : 'Ex-operator' },
      { name: CTO_NAMES[i % 5], role: 'Co-founder & CTO', note: margin >= 70 ? 'Technical' : 'Product' },
    ],
    memo1, memo2, fits, flags,
  };
}

export const COMPANIES: Company[] = RAW.map(build);

export function companyById(id: number): Company | undefined {
  return COMPANIES.find((c) => c.id === id);
}
