/**
 * Shared gate copy — title, why, and CTA label — so banners, tiles, and
 * locked actions teach the same unlock path.
 */

export type GateReason = 'email' | 'payment' | 'verification' | null;

export type GateCopy = {
  title: string;
  body: string;
  cta: string;
};

export function gateCopy(reason: GateReason, side: 'founder' | 'investor' = 'founder'): GateCopy {
  if (reason === 'email') {
    return {
      title: 'Confirm your email',
      body:
        side === 'founder'
          ? 'Needed before you can save audits, upload documents, or publish.'
          : 'Needed before you can express interest or request introductions.',
      cta: 'Confirm email',
    };
  }
  if (reason === 'payment') {
    return {
      title: 'Unlock FundReady AI',
      body: 'Your free trial has ended. One payment restores full access.',
      cta: 'View unlock',
    };
  }
  if (reason === 'verification') {
    return {
      title: side === 'founder' ? 'Add registration details' : 'Verify your identity',
      body:
        side === 'founder'
          ? 'Optional for browsing — required before some publish and diligence steps.'
          : 'Coming soon. You can browse and express interest after confirming email.',
      cta: side === 'founder' ? 'Add registration' : 'Learn more',
    };
  }
  return {
    title: 'Continue',
    body: 'You have access to this feature.',
    cta: 'Open',
  };
}
