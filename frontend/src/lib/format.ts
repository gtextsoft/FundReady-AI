import { C } from '@/theme/tokens';

/** "Northwind Ledger" → "NL". Used for every avatar tile. */
export function initials(name: string): string {
  return name
    .split(' ')
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
}

/** 142000 → "$142k"; 610 → "$610". */
export function moneyShort(n: number): string {
  return n >= 1000 ? `$${(n / 1000).toFixed(0)}k` : `$${n}`;
}

/** MRR → ARR run-rate, e.g. 142000 → "$1.70M". */
export function arrLabel(mrr: number): string {
  return `$${((mrr * 12) / 1000000).toFixed(2)}M`;
}

export function growthLabel(n: number): string {
  return `${n > 0 ? '+' : ''}${n}%`;
}

export function growthColor(n: number): string {
  if (n >= 12) return C.signal;
  if (n >= 5) return C.bone;
  return C.flag;
}

/** Trailing six months, ending on the seed data's July snapshot. */
export const TREND_MONTHS = ['Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul'];
