/**
 * Design tokens, lifted verbatim from the SACI FundMe prototype.
 *
 * Tailwind classes cover most styling; this module exists for the places that
 * need a raw colour value — SVG strokes, chart bars, gradient stops, animated
 * style values and anything computed from data (score bands, growth colours).
 * Keep it in sync with tailwind.config.js.
 */

export const C = {
  ground: '#000000',
  surface1: '#0a0a0a',
  surface2: '#111111',
  surface3: '#141414',
  surface4: '#1a1a1a',

  lineSoft: '#141414',
  line: '#1f1f1f',
  lineStrong: '#262626',
  lineDash: '#2e2e2e',

  ink: '#ededed',
  inkMuted: '#a1a1a1',
  inkDim: '#666666',
  inkFaint: '#525252',
  inkGhost: '#3d3d3d',

  blue: '#0070f3',
  grn: '#0cce6b',
  amb: '#f5a623',
  red: '#ff4d4f',
} as const;

/** Geist ships one family per weight — pick weight by family, not fontWeight. */
export const Font = {
  regular: 'Geist_400Regular',
  medium: 'Geist_500Medium',
  semibold: 'Geist_600SemiBold',
  mono: 'GeistMono_400Regular',
  monoMedium: 'GeistMono_500Medium',
  monoSemibold: 'GeistMono_600SemiBold',
} as const;

/** Fundability bands. Drives the results ring and every score badge. */
export type Band = { label: string; color: string };

export function band(score: number): Band {
  if (score >= 75) return { label: 'Strong', color: C.grn };
  if (score >= 50) return { label: 'Promising', color: C.blue };
  if (score >= 30) return { label: 'Early', color: C.amb };
  return { label: 'Not ready', color: C.red };
}

/** Investor-side score colouring uses its own thresholds (75 / 60 / 45). */
export function scoreColor(n: number): string {
  if (n >= 75) return C.grn;
  if (n >= 60) return C.blue;
  if (n >= 45) return C.amb;
  return C.red;
}

export function scoreTint(n: number): string {
  if (n >= 75) return 'rgba(12,206,107,0.10)';
  if (n >= 60) return 'rgba(0,112,243,0.10)';
  if (n >= 45) return 'rgba(245,166,35,0.10)';
  return 'rgba(255,77,79,0.10)';
}

export function scoreBorder(n: number): string {
  if (n >= 75) return 'rgba(12,206,107,0.30)';
  if (n >= 60) return 'rgba(0,112,243,0.30)';
  if (n >= 45) return 'rgba(245,166,35,0.30)';
  return 'rgba(255,77,79,0.30)';
}
