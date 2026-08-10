/**
 * Design tokens for FundReady AI.
 *
 * Tailwind classes cover most styling via CSS variables set by the theme
 * provider. This module exists for SVG strokes, chart bars, gradient stops,
 * animated style values and anything computed from data (score bands).
 * Keep semantic names in sync with tailwind.config.js.
 */

export type ColorScheme = 'light' | 'dark';

export type Palette = {
  ground: string;
  surface1: string;
  surface2: string;
  surface3: string;
  surface4: string;
  lineSoft: string;
  line: string;
  lineStrong: string;
  lineDash: string;
  ink: string;
  inkMuted: string;
  inkDim: string;
  inkFaint: string;
  inkGhost: string;
  blue: string;
  grn: string;
  amb: string;
  red: string;
};

/** Dark palette — the original product look. */
export const darkPalette: Palette = {
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
};

/** Light palette — same accents, inverted grounds/ink. */
export const lightPalette: Palette = {
  ground: '#f7f7f7',
  surface1: '#ffffff',
  surface2: '#f0f0f0',
  surface3: '#e8e8e8',
  surface4: '#dedede',
  lineSoft: '#ececec',
  line: '#e0e0e0',
  lineStrong: '#d0d0d0',
  lineDash: '#c4c4c4',
  ink: '#111111',
  inkMuted: '#525252',
  inkDim: '#737373',
  inkFaint: '#8a8a8a',
  inkGhost: '#a3a3a3',
  blue: '#0070f3',
  grn: '#0a9f54',
  amb: '#c47d00',
  red: '#e03e40',
};

export function paletteFor(scheme: ColorScheme): Palette {
  return scheme === 'light' ? lightPalette : darkPalette;
}

/**
 * Default export used where a hook is unavailable (module-level helpers).
 * Prefer `useThemeColors()` in components so light mode stays correct.
 */
export const C = darkPalette;

/** Geist ships one family per weight — pick weight by family, not fontWeight. */
export const Font = {
  regular: 'Geist_400Regular',
  medium: 'Geist_500Medium',
  semibold: 'Geist_600SemiBold',
  mono: 'GeistMono_400Regular',
  monoMedium: 'GeistMono_500Medium',
  monoSemibold: 'GeistMono_600SemiBold',
} as const;

/** Product display name — no space between Fund and Ready. */
export const PRODUCT_NAME = 'FundReady AI';

/** Fundability bands. Drives the results ring and every score badge. */
export type Band = { label: string; color: string };

export function band(score: number, colors: Palette = C): Band {
  if (score >= 75) return { label: 'Strong', color: colors.grn };
  if (score >= 50) return { label: 'Promising', color: colors.blue };
  if (score >= 30) return { label: 'Early', color: colors.amb };
  return { label: 'Not ready', color: colors.red };
}

/** Investor-side score colouring uses its own thresholds (75 / 60 / 45). */
export function scoreColor(n: number, colors: Palette = C): string {
  if (n >= 75) return colors.grn;
  if (n >= 60) return colors.blue;
  if (n >= 45) return colors.amb;
  return colors.red;
}

export function scoreTint(n: number, colors: Palette = C): string {
  if (n >= 75) return 'rgba(12,206,107,0.10)';
  if (n >= 60) return 'rgba(0,112,243,0.10)';
  if (n >= 45) return 'rgba(245,166,35,0.10)';
  return 'rgba(255,77,79,0.10)';
}

export function scoreBorder(n: number, colors: Palette = C): string {
  if (n >= 75) return 'rgba(12,206,107,0.30)';
  if (n >= 60) return 'rgba(0,112,243,0.30)';
  if (n >= 45) return 'rgba(245,166,35,0.30)';
  return 'rgba(255,77,79,0.30)';
}

/** CSS custom properties for NativeWind `vars()`. */
export function themeVars(scheme: ColorScheme): Record<string, string> {
  const p = paletteFor(scheme);
  return {
    '--color-ground': p.ground,
    '--color-surface-1': p.surface1,
    '--color-surface-2': p.surface2,
    '--color-surface-3': p.surface3,
    '--color-surface-4': p.surface4,
    '--color-line-soft': p.lineSoft,
    '--color-line': p.line,
    '--color-line-strong': p.lineStrong,
    '--color-line-dash': p.lineDash,
    '--color-ink': p.ink,
    '--color-ink-muted': p.inkMuted,
    '--color-ink-dim': p.inkDim,
    '--color-ink-faint': p.inkFaint,
    '--color-ink-ghost': p.inkGhost,
    '--color-blue': p.blue,
    '--color-grn': p.grn,
    '--color-amb': p.amb,
    '--color-red': p.red,
  };
}
