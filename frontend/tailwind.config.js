/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        // FundReady brand v1.0 — see FundReady-Brand-Pack/tokens/brand-tokens.json.
        // Obsidian base, one rationed accent. Keep in sync with src/theme/tokens.ts.

        // Base surface. The default state of every screen.
        obsidian: '#0C0F0E',
        // Cards, sheets, raised surfaces. `carbon` is the brand value; the other
        // three are an elevation ramp interpolated around it, because the app
        // needs four distinct raised levels and the brand sheet names one.
        carbon: {
          low: '#101415',
          DEFAULT: '#14181A',
          high: '#1A1F21',
          top: '#202628',
        },
        // Borders, dividers, inactive. `DEFAULT` is the brand's border token and
        // `bright` is brand Graphite; `soft` and `strong` fill out the ramp.
        graphite: {
          soft: '#1A2021',
          DEFAULT: '#23292A',
          strong: '#2C3335',
          bright: '#3A4340',
        },
        // Text on dark, in descending contrast. The first four are the brand's
        // text ramp; `ghost` is the near-invisible step the app already relied on.
        bone: {
          DEFAULT: '#EDF0EA',
          secondary: '#C3CBC5',
          muted: '#8A948E',
          faint: '#6E7873',
          ghost: '#4A534E',
        },
        // AI output and primary action. Nothing else — never fill an area larger
        // than a button with it. `ink` is the variant for light backgrounds.
        signal: {
          DEFAULT: '#C6F24E',
          ink: '#5F8A00',
        },
        // A specific, fixable gap. Never decorative.
        flag: '#FF7A3D',
        // Not brand tokens: the score bands need four separable hues and the
        // brand sheet defines two. Both are tuned to sit on obsidian beside
        // signal — use them for score bands and status only, never for chrome.
        info: '#4EA8F2',
        alert: '#F2554E',
      },
      fontFamily: {
        // Archivo ships one file per weight, so weight is selected by family.
        // `font-semibold` and friends are inert on custom fonts — use these.
        sans: ['Archivo_400Regular'],
        med: ['Archivo_500Medium'],
        semi: ['Archivo_600SemiBold'],
        bold: ['Archivo_700Bold'],
        mono: ['JetBrainsMono_400Regular'],
        'mono-med': ['JetBrainsMono_500Medium'],
        'mono-semi': ['JetBrainsMono_600SemiBold'],
      },
      fontSize: {
        // The brand type scale. Pair each with the family that carries its
        // weight — `text-display font-bold`, `text-label font-mono`.
        display: ['56px', { lineHeight: '1', letterSpacing: '-0.02em' }],
        title: ['34px', { lineHeight: '1.1', letterSpacing: '-0.015em' }],
        heading: ['20px', { lineHeight: '1.3' }],
        body: ['16px', { lineHeight: '1.55' }],
        data: ['15px', { lineHeight: '1.4' }],
        label: ['11px', { lineHeight: '1.2', letterSpacing: '0.16em' }],
      },
      borderRadius: {
        sm: '4px',
        md: '6px',
        lg: '8px',
        xl: '10px',
      },
    },
  },
  plugins: [],
};
