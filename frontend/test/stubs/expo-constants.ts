/**
 * No Expo dev server in a test process, so neither host hint is populated.
 * `resolveBaseUrl` then falls through to `EXPO_PUBLIC_API_URL`, which
 * `test/setup.ts` pins.
 */
export default {
  expoConfig: null as { hostUri?: string } | null,
  expoGoConfig: null as { debuggerHost?: string } | null,
};
