/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Semantic colours — values come from CSS vars set by the theme root.
        ground: 'var(--color-ground)',
        surface: {
          1: 'var(--color-surface-1)',
          2: 'var(--color-surface-2)',
          3: 'var(--color-surface-3)',
          4: 'var(--color-surface-4)',
        },
        line: {
          soft: 'var(--color-line-soft)',
          DEFAULT: 'var(--color-line)',
          strong: 'var(--color-line-strong)',
          dash: 'var(--color-line-dash)',
        },
        ink: {
          DEFAULT: 'var(--color-ink)',
          muted: 'var(--color-ink-muted)',
          dim: 'var(--color-ink-dim)',
          faint: 'var(--color-ink-faint)',
          ghost: 'var(--color-ink-ghost)',
        },
        blue: 'var(--color-blue)',
        grn: 'var(--color-grn)',
        amb: 'var(--color-amb)',
        red: 'var(--color-red)',
      },
      fontFamily: {
        // Geist ships one family per weight, so weight is selected by family.
        // `font-semibold` and friends are inert on custom fonts — use these.
        sans: ['Geist_400Regular'],
        med: ['Geist_500Medium'],
        semi: ['Geist_600SemiBold'],
        mono: ['GeistMono_400Regular'],
        'mono-med': ['GeistMono_500Medium'],
        'mono-semi': ['GeistMono_600SemiBold'],
      },
    },
  },
  plugins: [],
};
