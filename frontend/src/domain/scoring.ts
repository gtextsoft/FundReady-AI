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

/**
 * The Fundability Score, out of 100, across five weighted components.
 * Ported from the prototype so scores stay identical to the design.
 *
 * When the backend takes ownership of scoring, keep this as the offline
 * fallback — the onboarding form shows a live score before submission.
 */
export function scoreParts(f: FounderProfile): ScorePart[] {
  const monthlyRevenue = f.revModel === 'ARR' ? num(f.revenue) / 12 : num(f.revenue);

  const traction =
    Math.min(18, monthlyRevenue > 0 ? (Math.log10(monthlyRevenue + 1) / Math.log10(500000)) * 18 : 0) +
    Math.min(12, (num(f.growth) / 25) * 12);

  const ltvcac = num(f.cac) > 0 ? num(f.ltv) / num(f.cac) : 0;
  const econ = Math.min(13, (num(f.margin) / 85) * 13) + Math.min(12, (ltvcac / 3.5) * 12);

  const market = Math.min(20, num(f.tam) > 0 ? (Math.log10(num(f.tam) + 1) / Math.log10(50)) * 20 : 0);

  const team = Math.min(8, num(f.founders) * 3.2) + (f.technical === 'Yes' ? 7 : f.technical === 'No' ? 2 : 0);

  const ready = (f.deck ? 6 : 0) + (STAGE_BONUS[f.stage] ?? 0) * 0.66;

  return [
    { key: 'Traction & revenue', value: traction, max: 30 },
    { key: 'Unit economics', value: econ, max: 25 },
    { key: 'Market size', value: market, max: 20 },
    { key: 'Team', value: team, max: 15 },
    { key: 'Readiness', value: Math.min(10, ready), max: 10 },
  ];
}

export function scoreOf(f: FounderProfile): number {
  return Math.round(scoreParts(f).reduce((a, p) => a + p.value, 0));
}

export function ltvCacRatio(f: FounderProfile): number {
  return num(f.cac) > 0 ? num(f.ltv) / num(f.cac) : 0;
}

export function strengths(f: FounderProfile): Insight[] {
  const out: Insight[] = [];
  if (num(f.growth) >= 15)
    out.push({ title: 'Compounding growth', body: `${num(f.growth)}% MoM puts you in the top decile of submissions at this stage.` });
  if (num(f.margin) >= 70)
    out.push({ title: 'Software-grade margins', body: `${num(f.margin)}% gross margin supports efficient scaling without capital drag.` });
  if (f.technical === 'Yes')
    out.push({ title: 'Technical founding team', body: 'In-house engineering leadership de-risks delivery and reduces burn.' });
  if (num(f.cac) > 0 && ltvCacRatio(f) >= 3)
    out.push({ title: 'Healthy LTV:CAC', body: `${ltvCacRatio(f).toFixed(1)}:1 payback profile clears the 3:1 institutional threshold.` });
  if (num(f.tam) >= 5)
    out.push({ title: 'Large addressable market', body: `$${num(f.tam)}B TAM leaves room for a venture-scale outcome.` });
  if (!out.length)
    out.push({ title: 'Submission on record', body: 'Baseline profile captured. Complete every field to surface strengths.' });
  return out.slice(0, 3);
}

export function risks(f: FounderProfile): Insight[] {
  const out: Insight[] = [];
  if (!f.deck)
    out.push({ title: 'No deck on file', body: 'Investors cannot progress without a deck or financial model. Highest-leverage fix.' });
  if (num(f.growth) < 8)
    out.push({ title: 'Flat growth trajectory', body: `${num(f.growth) || 0}% MoM is below the 8% floor most seed funds screen on.` });
  if (num(f.cac) === 0 || num(f.ltv) === 0)
    out.push({ title: 'Unit economics unproven', body: 'CAC and LTV are missing — the single most common reason for a pass.' });
  else if (ltvCacRatio(f) < 3)
    out.push({ title: 'Payback too long', body: `${ltvCacRatio(f).toFixed(1)}:1 LTV:CAC signals acquisition spend outruns value.` });
  if (num(f.margin) < 50 && num(f.margin) > 0)
    out.push({ title: 'Margin compression', body: `${num(f.margin)}% gross margin caps how far each dollar of revenue travels.` });
  if (num(f.tam) < 1)
    out.push({ title: 'Constrained TAM', body: 'Sub-$1B market ceilings limit venture upside; consider a PE-style path.' });
  return out.slice(0, 3);
}

function vcFit(score: number): Fit {
  return score >= 70 ? 'High' : score >= 45 ? 'Moderate' : 'Low';
}

function peFit(f: FounderProfile, score: number): Fit {
  if (num(f.margin) >= 60 && score >= 40) return 'High';
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
