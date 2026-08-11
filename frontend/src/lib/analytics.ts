/**
 * Analytics seam for PRD success metrics (T5.4 / F5.x).
 * No third-party SDK yet — events are logged in __DEV__ only.
 */

type Props = Record<string, string | number | boolean | null | undefined>;

export function track(event: string, props?: Props): void {
  if (__DEV__) {
    // eslint-disable-next-line no-console
    console.info('[analytics]', event, props ?? {});
  }
}

export const AnalyticsEvents = {
  auditQueued: 'audit_queued',
  interestExpressed: 'interest_expressed',
  kycStarted: 'kyc_started',
  unlockCheckoutOpened: 'unlock_checkout_opened',
  programmeEnrolled: 'programme_enrolled',
} as const;
