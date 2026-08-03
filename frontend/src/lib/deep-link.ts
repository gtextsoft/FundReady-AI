/**
 * Tokens arriving on a link from an email.
 *
 * The backend sends `{APP_LINK_BASE_URL}/verify-email?token=…` and
 * `{APP_LINK_BASE_URL}/reset-password?token=…` — links that point at **this
 * app**, not at the API. That is deliberate on both sides: mail security
 * scanners prefetch every URL in a message, so a `GET` endpoint on the API
 * would have its single-use token spent before the recipient ever clicked. The
 * client lifts the token out and `POST`s it.
 *
 * There is no URL parser here on purpose. expo-router's own linking already
 * resolves `sacifundme://reset-password?token=x`, the Expo Go form
 * (`exp://10.0.0.2:8081/--/reset-password?token=x`) and the plain web URL onto
 * the same route with the same search params — a hand-rolled parser would be a
 * second, worse implementation of something already in the bundle. What is left
 * is reading one parameter safely, which is what this file does.
 *
 * **Not yet wired: https links do not open the app.** Universal Links (iOS
 * `associatedDomains`) and App Links (Android `intentFilters`) are not
 * configured in `app.json`, so an emailed `https://` link opens the browser
 * instead. Until that lands with the deployed host, `APP_LINK_BASE_URL` has to
 * be the `sacifundme://` scheme for a link to reach a phone. Both screens keep
 * a paste-the-code field for exactly that reason.
 */

/** What expo-router hands back from `useLocalSearchParams()`. */
export type LinkParams = Record<string, string | string[] | undefined>;

/**
 * The token from a link parameter, or null when there is not one.
 *
 * A repeated query parameter arrives as an array; the first entry wins, because
 * a link carrying two tokens is malformed and guessing the second would be no
 * better. Whitespace is trimmed — mail clients wrap long URLs, and a copied
 * token routinely picks up a trailing newline.
 */
export function tokenFromParams(params: LinkParams, key: string = 'token'): string | null {
  const raw = params[key];
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}
