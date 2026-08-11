import { Pressable, View } from 'react-native';
import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { daysLeftInTrial, hasAccess, isPaid, TRIAL_DAYS } from '@/domain/access';
import type { FounderAccount } from '@/domain/types';

type Tone = 'info' | 'warn' | 'danger' | 'ok';

const TONE: Record<Tone, { border: string; bg: string; accent: string }> = {
  info: { border: 'rgba(78,168,242,0.35)', bg: 'rgba(78,168,242,0.08)', accent: C.info },
  warn: { border: 'rgba(255,122,61,0.35)', bg: 'rgba(255,122,61,0.08)', accent: C.flag },
  danger: { border: '#4A1F1E', bg: 'rgba(242,85,78,0.08)', accent: C.alert },
  ok: { border: 'rgba(198,242,78,0.30)', bg: 'rgba(198,242,78,0.07)', accent: C.signal },
};

/**
 * The one thing the founder most needs to act on, at the top of the dashboard.
 *
 * Priority is deliberate: an expired trial outranks verification, because
 * verifying while locked out would not give them the product back.
 */
export function StatusBanner({
  account,
  onUnlock,
  onVerify,
  onConfirmEmail,
}: {
  account: FounderAccount;
  onUnlock: () => void;
  onVerify: () => void;
  onConfirmEmail: () => void;
}) {
  const locked = !hasAccess(account);
  const days = daysLeftInTrial(account);

  // Ahead of everything else: it is the cheapest gate to clear and it blocks
  // the same things company verification does.
  if (!account.emailVerified) {
    return (
      <Banner
        tone="warn"
        eyebrow="CONFIRM YOUR EMAIL"
        title="Confirm your email address"
        body="We need to know you control this address before investors can see you, or before you can upload documents."
        cta="Confirm email"
        onPress={onConfirmEmail}
      />
    );
  }

  if (locked) {
    return (
      <Banner
        tone="danger"
        eyebrow="TRIAL ENDED"
        title="Unlock FundReady to continue"
        body={`Your ${TRIAL_DAYS}-day trial has finished. A single one-off payment restores everything, permanently.`}
        cta="See what's included"
        onPress={onUnlock}
      />
    );
  }

  if (account.verification === 'in_review') {
    return (
      <Banner
        tone="info"
        eyebrow="VERIFICATION IN REVIEW"
        title="We're checking your registration"
        body="This usually takes a few minutes. You'll get a notification the moment it clears."
      />
    );
  }

  if (account.verification === 'rejected') {
    return (
      <Banner
        tone="danger"
        eyebrow="VERIFICATION FAILED"
        title="We couldn't confirm your registration"
        body="The details didn't match the registry. Check the number and resubmit."
        cta="Try again"
        onPress={onVerify}
      />
    );
  }

  if (account.verification === 'unverified') {
    return (
      <Banner
        tone="warn"
        eyebrow={`TRIAL · ${days} ${days === 1 ? 'DAY' : 'DAYS'} LEFT`}
        title="Verify your company to be seen by investors"
        body="Until your registration is confirmed you stay off the dealflow list and the AI mentor is locked."
        cta="Verify company"
        onPress={onVerify}
      />
    );
  }

  // Verified, and either paid or still inside the trial.
  if (isPaid(account)) return null;

  return (
    <Banner
      tone="ok"
      eyebrow={`TRIAL · ${days} ${days === 1 ? 'DAY' : 'DAYS'} LEFT`}
      title="You're live in the investor dealflow"
      body="Everything is unlocked for the rest of your trial. Unlock permanently whenever you're ready."
      cta="Unlock permanently"
      onPress={onUnlock}
    />
  );
}

function Banner({
  tone,
  eyebrow,
  title,
  body,
  cta,
  onPress,
}: {
  tone: Tone;
  eyebrow: string;
  title: string;
  body: string;
  cta?: string;
  onPress?: () => void;
}) {
  const t = TONE[tone];
  return (
    <View className="rounded-[12px] p-[14px]" style={{ borderWidth: 1, borderColor: t.border, backgroundColor: t.bg }}>
      <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: t.accent }}>
        {eyebrow}
      </Mono>
      <TxtSemi className="mb-[5px] mt-[9px] text-[15px]" style={{ letterSpacing: -0.3 }}>
        {title}
      </TxtSemi>
      <Txt className="text-[12.5px] text-bone-secondary" style={{ lineHeight: 19 }}>
        {body}
      </Txt>
      {cta && onPress ? (
        <Pressable accessibilityRole="button" onPress={onPress} className="mt-3 self-start" hitSlop={8}>
          <TxtSemi className="text-[12.5px]" style={{ color: t.accent }}>
            {cta} →
          </TxtSemi>
        </Pressable>
      ) : null}
    </View>
  );
}
