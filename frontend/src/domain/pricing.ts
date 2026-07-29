/**
 * The one-off unlock price.
 *
 * PLACEHOLDER — set by the business, not by the app. Everything that shows a
 * price reads it from here, so changing it is a one-line edit. When the
 * backend owns billing it should return this from the server instead, since
 * price changes must not require an app release.
 *
 * Note for whoever wires the payment rail: Apple and Google both require their
 * own in-app purchase for digital goods consumed inside the app. A card
 * checkout via Paystack/Flutterwave is fine on Android sideloads and the web
 * build, but shipping this on the App Store as a card payment will fail
 * review. That decision belongs with the payment work, not here.
 */
export const UNLOCK_PRICE = {
  currency: 'USD',
  symbol: '$',
  amount: 149,
  /** What the founder sees. */
  label: '$149',
  cadence: 'one-time',
} as const;

export const UNLOCK_BENEFITS = [
  'Listed in the investor dealflow database',
  'Unlimited AI mentor sessions on your metrics',
  'Accept introductions and virtual calls from investors',
  'Re-run your Fundability assessment any time',
  'Both growth programmes, for as long as you need them',
];
