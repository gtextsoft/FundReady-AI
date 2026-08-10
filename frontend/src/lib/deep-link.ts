/**
 * Safe reading of query parameters that arrive on a route.
 *
 * Auth secrets (email verification, password reset) are six-digit codes typed
 * into the app — they are not carried in emailed links. This helper remains
 * for ordinary query params (e.g. `?email=` prefill, `?next=onboarding`).
 *
 * There is no URL parser here on purpose. expo-router's own linking already
 * resolves scheme, Expo Go, and plain web URLs onto the same route with the
 * same search params.
 */

/** What expo-router hands back from `useLocalSearchParams()`. */
export type LinkParams = Record<string, string | string[] | undefined>;

/**
 * A string query parameter, or null when there is not one.
 *
 * A repeated query parameter arrives as an array; the first entry wins.
 * Whitespace is trimmed — mail clients and copy-paste routinely add a trailing
 * newline.
 */
export function tokenFromParams(params: LinkParams, key: string = 'token'): string | null {
  const raw = params[key];
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}
