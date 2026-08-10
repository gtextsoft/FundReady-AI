/**
 * Runs before each test file, in a fresh module registry.
 *
 * `api/http.ts` resolves its base URL once at import time, so it has to be
 * pinned here rather than per-test — otherwise the first test file to import
 * the module fixes it for all of them.
 */
process.env.EXPO_PUBLIC_API_URL = 'http://api.test';

/** The `localStorage` that `lib/storage.ts` uses on its web branch. */
const store = new Map<string, string>();

Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
  },
});

beforeEach(() => {
  store.clear();
});
