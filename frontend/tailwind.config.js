/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        // Grounds — every surface in the prototype sits on one of these.
        ground: '#000000',
        surface: {
          1: '#0a0a0a',
          2: '#111111',
          3: '#141414',
          4: '#1a1a1a',
        },
        // Hairlines, in ascending contrast.
        line: {
          soft: '#141414',
          DEFAULT: '#1f1f1f',
          strong: '#262626',
          dash: '#2e2e2e',
        },
        ink: {
          DEFAULT: '#ededed',
          muted: '#a1a1a1',
          dim: '#666666',
          faint: '#525252',
          ghost: '#3d3d3d',
        },
        blue: '#0070f3',
        grn: '#0cce6b',
        amb: '#f5a623',
        red: '#ff4d4f',
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
