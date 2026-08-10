import type { Href } from 'expo-router';
import type { Role } from '@/api';

/**
 * Route helpers.
 *
 * Typed routes emit `/founder/index` style paths while the runtime uses the
 * bare forms, so hrefs are cast once here rather than at every call site.
 */

export const FOUNDER_HOME = '/founder' as Href;
export const INVESTOR_HOME = '/investor' as Href;
export const SIGN_IN = '/sign-in' as Href;
export const SIGN_UP = '/sign-up' as Href;
export const ONBOARDING = '/onboarding' as Href;
export const VERIFY_EMAIL = '/verify-email' as Href;
export const MFA = '/mfa' as Href;
export const FORGOT_PASSWORD = '/forgot-password' as Href;

/**
 * The one route an emailed link still lands on. The backend builds it as
 * `{APP_LINK_BASE_URL}/reset-password?token=…`, so **this path segment is a
 * contract with the server** — renaming it breaks every reset link already
 * sitting in someone's inbox. (Verification moved to a six-digit code, so
 * `VERIFY_EMAIL` above is an in-app destination only.)
 */
export const RESET_PASSWORD = '/reset-password' as Href;

/** Where a role belongs after authenticating. */
export function homeFor(role: Role): Href {
  return role === 'investor' ? INVESTOR_HOME : FOUNDER_HOME;
}

export const route = (path: string) => path as Href;
