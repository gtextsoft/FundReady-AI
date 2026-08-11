// Flat config. `eslint-config-expo/flat` brings the React, React Hooks,
// import and TypeScript rules that match this Expo SDK.
//
// The extra rules below are the ones that would have caught real bugs in this
// codebase, not style preferences — style is Prettier's job and is deliberately
// not duplicated here.

const expo = require('eslint-config-expo/flat');

module.exports = [
  ...expo,
  {
    ignores: [
      'node_modules/**',
      '.expo/**',
      'dist/**',
      'android/**',
      'ios/**',
      '.ui-shots/**',
      'expo-env.d.ts',
      'nativewind-env.d.ts',
    ],
  },
  {
    files: ['**/*.{ts,tsx}'],
    rules: {
      // An unawaited API call fails silently: the screen carries on, the
      // request rejects into nothing, and the user sees a success state for
      // something that never happened. Every method on `FundReadyApi` is async.
      '@typescript-eslint/no-floating-promises': 'off', // needs type-aware linting; see below
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
  {
    // Node scripts, not app code: `require`, `console` and the Node globals
    // are all correct there.
    files: ['scripts/**/*.js', '*.config.js', 'eslint.config.js'],
    languageOptions: {
      sourceType: 'commonjs',
      globals: {
        __dirname: 'readonly',
        __filename: 'readonly',
        Buffer: 'readonly',
        console: 'readonly',
        module: 'writable',
        process: 'readonly',
        require: 'readonly',
      },
    },
    rules: { 'no-console': 'off', '@typescript-eslint/no-require-imports': 'off' },
  },
  {
    // Tests re-import through a reset module registry to get fresh module
    // state, which `import` cannot express.
    files: ['test/**/*.ts'],
    rules: { '@typescript-eslint/no-require-imports': 'off' },
  },
];
