import { band } from '@/theme/tokens';
import type { Assessment, Fit, FounderProfile, Insight, ScorePart } from './types';

/** Tolerant numeric parse — form fields carry "$48,000" and "14%" alike. */
export function num(v: string | number): number {
  const n = parseFloat(String(v).replace(/[^0-9.\-]/g, ''));
  return isNaN(n) ? 0 : n;
}

const STAGE_BONUS: Record<string, number> = {
  'Pre-seed': 2,
  Seed: 4,
  'Series A': 6,
  Bootstrapped: 3,
};

/** Monthly revenue, whichever unit the founder chose to state it in. */
export function monthlyRevenue(f: FounderProfile): number {
  return f.revModel === 'ARR' ? num(f.revenue) / 12 : num(f.revenue);
}

/**
 * Gross margin, **derived** rather than asked.
 *
 * `(revenue - cost of revenue) / revenue`, which is the same arithmetic the
 * server's `finance.py` performs. The form used to ask the founder for this
 * number directly; it no longer does, because a figure nobody can check is
 * exactly what the audit rubric marks down. Returns null when it cannot be
 * computed, which is different from zero.
 */
export function grossMarginPercent(f: FounderProfile): number | null {
  const revenue = monthlyRevenue(f);
  if (revenue <= 0) return null;
  const cost = num(f.costOfRevenue);
  if (!f.costOfRevenue.trim()) return null;
  return ((revenue - cost) / revenue) * 100;
}

/**
 * Lifetime value, **margin-adjusted**: `(ARPU x gross margin) / churn`.
 *
 * The margin adjustment matches the server deliberately. The commoner
 * shortcut, raw `ARPU / churn`, materially overstates a low-margin business --
 * revenue a company does not keep is not value. Two provisional figures that
 * disagree would be worse than one.
 */
export function lifetimeValue(f: FounderProfile): number | null {
  const arpu = num(f.arpu);
  const churn = num(f.churn);
  if (arpu <= 0 || churn <= 0) return null;
  const margin = grossMarginPercent(f);
  const adjusted = margin === null ? arpu : arpu * (margin / 100);
  return adjusted / (churn / 100);
}

/**
 * The Fundability Score, out of 100, across five weighted components.
 *
 * **Scaffolding with a demolition date.** This is a heuristic over the form,
 * not an audit, and the results screen labels it provisional. It exists only
 * so onboarding can show something before the real engine lands; two scoring
 * models, one of which is not the audit, is precisely the false-verdict
 * failure the platform exists to prevent. Delete it when T2.7/T2.8 ship.
 */
export function scoreParts(f: FounderProfile): ScorePart[] {
  const revenue = monthlyRevenue(f);

  // Revenue scale only. Growth was asked as a single percentage, which cannot
  // distinguish a trend from one good month -- the server wants a history
  // instead, and until it stores one there is nothing honest to score here.
  const traction = Math.min(
    30,
    revenue > 0 ? (Math.log10(revenue + 1) / Math.log10(500000)) * 30 : 0,
  );

  const ltv = lifetimeValue(f);
  const ltvcac = ltv !== null && num(f.cac) > 0 ? ltv / num(f.cac) : 0;
  const margin = grossMarginPercent(f);
  const econ =
    Math.min(13, margin !== null ? (Math.max(0, margin) / 85) * 13 : 0) +
    Math.min(12, (ltvcac / 3.5) * 12);

  // Retention stands in for market size. Market sizing now needs a bottom-up
  // derivation the profile cannot hold yet, and a made-up number would be
  // worse than a smaller, real signal.
  const churn = num(f.churn);
  const retention = churn > 0 ? Math.min(20, (5 / churn) * 20) : 0;

  const founders = Math.min(8, num(f.founders) * 3.2);
  const commitment = num(f.foundersFullTime) > 0 ? 7 : 0;
  const team = founders + commitment;

  const ready = (f.deck ? 6 : 0) + (STAGE_BONUS[f.stage] ?? 0) * 0.66;

  return [
    { key: 'Traction & revenue', value: traction, max: 30 },
    { key: 'Unit economics', value: econ, max: 25 },
    { key: 'Retention', value: retention, max: 20 },
    { key: 'Team', value: team, max: 15 },
    { key: 'Readiness', value: Math.min(10, ready), max: 10 },
  ];
}

export function scoreOf(f: FounderProfile): number {
  return Math.round(scoreParts(f).reduce((a, p) => a + p.value, 0));
}

export function ltvCacRatio(f: FounderProfile): number {
  const ltv = lifetimeValue(f);
  return ltv !== null && num(f.cac) > 0 ? ltv / num(f.cac) : 0;
}

/** Months of runway the stated cash and burn imply, or null when unknowable. */
export function runwayMonths(f: FounderProfile): number | null {
  const burn = num(f.costs) - monthlyRevenue(f);
  if (burn <= 0) return null; // profitable, or not enough given to say
  const cash = num(f.cash);
  if (cash <= 0) return null;
  return cash / burn;
}

export function strengths(f: FounderProfile): Insight[] {
  const out: Insight[] = [];
  const margin = grossMarginPercent(f);
  const runway = runwayMonths(f);

  if (margin !== null && margin >= 70)
    out.push({ title: 'Software-grade margins', body: `${margin.toFixed(0)}% gross margin supports scaling without capital drag.` });
  if (num(f.costs) > 0 && monthlyRevenue(f) >= num(f.costs))
    out.push({ title: 'Covering its costs', body: 'Revenue meets monthly costs, which removes the usual urgency from a raise.' });
  if (runway !== null && runway >= 18)
    out.push({ title: 'Long runway', body: `${runway.toFixed(0)} months of cash gives you room to raise on your own timetable.` });
  if (num(f.cac) > 0 && ltvCacRatio(f) >= 3)
    out.push({ title: 'Healthy LTV:CAC', body: `${ltvCacRatio(f).toFixed(1)}:1 clears the 3:1 threshold most funds screen on.` });
  if (num(f.churn) > 0 && num(f.churn) <= 3)
    out.push({ title: 'Customers stay', body: `${num(f.churn)}% monthly churn is strong retention and lifts every other number.` });
  if (f.ipOwned === 'Yes' && f.contractsTransferable === 'Yes')
    out.push({ title: 'Clean to acquire', body: 'Company-owned IP and transferable contracts remove the usual diligence blockers.' });
  if (!out.length)
    out.push({ title: 'Submission on record', body: 'Baseline profile captured. Complete every field to surface strengths.' });
  return out.slice(0, 3);
}

export function risks(f: FounderProfile): Insight[] {
  const out: Insight[] = [];
  const margin = grossMarginPercent(f);
  const runway = runwayMonths(f);

  if (!f.deck)
    out.push({ title: 'No deck on file', body: 'Investors cannot progress without a deck or financial model. Highest-leverage fix.' });
  if (runway !== null && runway < 6)
    out.push({ title: 'Short runway', body: `${runway.toFixed(0)} months of cash. Below six, a raise happens on the investor's terms, not yours.` });
  if (num(f.cac) === 0 || num(f.arpu) === 0 || num(f.churn) === 0)
    out.push({ title: 'Unit economics unproven', body: 'CAC, revenue per customer and churn are what prove a business works. Missing them is the commonest reason for a pass.' });
  else if (ltvCacRatio(f) < 3)
    out.push({ title: 'Payback too long', body: `${ltvCacRatio(f).toFixed(1)}:1 LTV:CAC signals acquisition spend outruns value.` });
  if (margin !== null && margin > 0 && margin < 50)
    out.push({ title: 'Margin compression', body: `${margin.toFixed(0)}% gross margin caps how far each unit of revenue travels.` });
  if (f.ipOwned === 'No')
    out.push({ title: 'IP is not company-owned', body: 'Work owned by individuals rather than the company stops most acquisitions and many raises.' });
  if (!f.description.trim() || !f.businessModel.trim())
    out.push({ title: 'The basics are missing', body: 'What you do and how you make money are the first things any reader needs.' });
  return out.slice(0, 3);
}

function vcFit(score: number): Fit {
  return score >= 70 ? 'High' : score >= 45 ? 'Moderate' : 'Low';
}

function peFit(f: FounderProfile, score: number): Fit {
  const margin = grossMarginPercent(f);
  if (margin !== null && margin >= 60 && score >= 40) return 'High';
  return score >= 35 ? 'Moderate' : 'Low';
}

/** Full assessment. The mock API returns this; the backend should mirror it. */
export function assess(f: FounderProfile): Assessment {
  const parts = scoreParts(f);
  const score = Math.round(parts.reduce((a, p) => a + p.value, 0));
  const b = band(score);
  return {
    score,
    parts,
    bandLabel: b.label,
    bandColor: b.color,
    vcFit: vcFit(score),
    peFit: peFit(f, score),
    strengths: strengths(f),
    risks: risks(f),
    route: score < 50 ? 'readiness' : 'wealth',
  };
}
