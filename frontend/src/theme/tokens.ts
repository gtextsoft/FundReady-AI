/**
 * FundReady brand tokens v1.0.
 *
 * Tailwind classes cover most styling; this module exists for the places that
 * need a raw colour value — SVG strokes, chart bars, gradient stops, animated
 * style values and anything computed from data (score bands, growth colours).
 * Keep it in sync with tailwind.config.js.
 *
 * Signal green is rationed: if a user can't press it and the AI didn't produce
 * it, it isn't green. Never fill an area larger than a button with it.
 */

export const C = {
  /** Base surface. The default state of every screen. */
  obsidian: '#0C0F0E',

  /** Cards, sheets, raised surfaces, in ascending elevation. */
  carbonLow: '#101415',
  carbon: '#14181A',
  carbonHigh: '#1A1F21',
  carbonTop: '#202628',

  /** Borders, dividers, inactive, in ascending contrast. */
  graphiteSoft: '#1A2021',
  graphite: '#23292A',
  graphiteStrong: '#2C3335',
  graphiteBright: '#3A4340',

  /** Text on dark, in descending contrast. */
  bone: '#EDF0EA',
  boneSecondary: '#C3CBC5',
  boneMuted: '#8A948E',
  boneFaint: '#6E7873',
  boneGhost: '#4A534E',

  /** AI output and primary action. Nothing else. */
  signal: '#C6F24E',
  /** Signal green on light backgrounds only — it fails contrast on bone otherwise. */
  signalInk: '#5F8A00',

  /** A specific, fixable gap. Never decorative. */
  flag: '#FF7A3D',

  /**
   * Not brand tokens. The score bands need four separable hues and the brand
   * sheet defines two, so these are tuned to sit on obsidian beside signal.
   * Score bands and status only — never chrome.
   */
  info: '#4EA8F2',
  alert: '#F2554E',
} as const;

/** Archivo ships one file per weight — pick weight by family, not fontWeight. */
export const Font = {
  regular: 'Archivo_400Regular',
  medium: 'Archivo_500Medium',
  semibold: 'Archivo_600SemiBold',
  bold: 'Archivo_700Bold',
  mono: 'JetBrainsMono_400Regular',
  monoMedium: 'JetBrainsMono_500Medium',
  monoSemibold: 'JetBrainsMono_600SemiBold',
} as const;

/** Fundability bands. Drives the results ring and every score badge. */
export type Band = { label: string; color: string };

export function band(score: number): Band {
  if (score >= 75) return { label: 'Strong', color: C.signal };
  if (score >= 50) return { label: 'Promising', color: C.info };
  if (score >= 30) return { label: 'Early', color: C.flag };
  return { label: 'Not ready', color: C.alert };
}

/** Investor-side score colouring uses its own thresholds (75 / 60 / 45). */
export function scoreColor(n: number): string {
  if (n >= 75) return C.signal;
  if (n >= 60) return C.info;
  if (n >= 45) return C.flag;
  return C.alert;
}

export function scoreTint(n: number): string {
  if (n >= 75) return 'rgba(198,242,78,0.10)';
  if (n >= 60) return 'rgba(78,168,242,0.10)';
  if (n >= 45) return 'rgba(255,122,61,0.10)';
  return 'rgba(242,85,78,0.10)';
}

export function scoreBorder(n: number): string {
  if (n >= 75) return 'rgba(198,242,78,0.30)';
  if (n >= 60) return 'rgba(78,168,242,0.30)';
  if (n >= 45) return 'rgba(255,122,61,0.30)';
  return 'rgba(242,85,78,0.30)';
}
