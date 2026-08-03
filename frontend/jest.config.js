/**
 * Tests for the logic that has to be right, not for the rendering.
 *
 * Deliberately **not** using `jest-expo`. Its peer range wants
 * `@react-native/jest-preset@^0.86.2` while `react-native@0.86.0` pins that
 * package to exactly `0.86.0`, so installing it needs `--legacy-peer-deps` —
 * which then makes `npm ci` in CI need the same flag, and a CI that has to be
 * told to ignore a broken dependency graph is not much of a gate.
 *
 * The cost of leaving it out is real and worth stating: **there are no
 * component rendering tests.** Every trap in `AGENTS.md` — dropped `className`,
 * two colour utilities on one element, nested `Pressable` — still needs
 * `scripts/verify-ui.js` driving a real browser. Jest here covers the
 * transport, the gates and the parsing; it does not cover the pixels.
 *
 * Native modules are mapped to stubs in `test/stubs/`, so nothing under
 * `node_modules/react-native` is ever loaded or transformed.
 */
module.exports = {
  testEnvironment: 'node',
  roots: ['<rootDir>/test'],
  testMatch: ['**/*.test.ts'],
  setupFilesAfterEnv: ['<rootDir>/test/setup.ts'],
  clearMocks: true,
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
    '^react-native$': '<rootDir>/test/stubs/react-native.ts',
    '^expo-constants$': '<rootDir>/test/stubs/expo-constants.ts',
    '^expo-secure-store$': '<rootDir>/test/stubs/expo-secure-store.ts',
    '^expo/virtual/env(\\.js)?$': '<rootDir>/test/stubs/expo-env.ts',
  },
};
