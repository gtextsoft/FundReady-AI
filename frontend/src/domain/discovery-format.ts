import type { ServerStage } from '@/api/profile-mapping';
import type { DiscoveryVerdict } from '@/domain/discovery';
import { C } from '@/theme/tokens';

/** Human labels for the server's stage enum on investor cards. */
export const STAGE_LABEL: Record<ServerStage, string> = {
  idea: 'Idea',
  pre_seed: 'Pre-seed',
  seed: 'Seed',
  series_a: 'Series A',
  series_b_plus: 'Series B+',
  growth: 'Growth',
};

/** Filter chips → wire stage. One stage per query (server accepts one). */
export const FILTER_STAGES: { label: string; value: ServerStage }[] = [
  { label: 'Pre-seed', value: 'pre_seed' },
  { label: 'Seed', value: 'seed' },
  { label: 'Series A', value: 'series_a' },
  { label: 'Growth', value: 'growth' },
];

export const FILTER_COUNTRIES: { label: string; value: string }[] = [
  { label: 'Nigeria', value: 'NG' },
  { label: 'Ghana', value: 'GH' },
  { label: 'Kenya', value: 'KE' },
  { label: 'South Africa', value: 'ZA' },
  { label: 'UAE', value: 'AE' },
  { label: 'United Kingdom', value: 'GB' },
  { label: 'United States', value: 'US' },
];

export function stageLabel(stage: ServerStage | null | undefined): string {
  if (!stage) return '—';
  return STAGE_LABEL[stage] ?? stage;
}

export function verdictLabel(level: string): string {
  return level.replace(/_/g, ' ');
}

/** Colour for audit verdict levels (not the prototype 0–100 bands). */
export function verdictColor(level: string): string {
  const n = level.toLowerCase();
  if (n === 'ready') return C.grn;
  if (n === 'provisional') return C.blue;
  if (n === 'not_yet') return C.amb;
  if (n === 'insufficient_data') return C.inkFaint;
  return C.inkMuted;
}

export function verdictScoreText(v: DiscoveryVerdict): string {
  if (v.score == null) return '—';
  return String(Math.round(v.score));
}
