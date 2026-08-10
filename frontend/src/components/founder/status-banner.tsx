import { Pressable, View } from 'react-native';
import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { daysLeftInTrial, hasAccess, isPaid, TRIAL_DAYS } from '@/domain/access';
import { gateCopy } from '@/domain/gate-copy';
import type { FounderAccount } from '@/domain/types';

type Tone = 'info' | 'warn' | 'danger' | 'ok';

const TONE: Record<Tone, { border: string; bg: string; accent: string }> = {
  info: { border: 'rgba(0,112,243,0.35)', bg: 'rgba(0,112,243,0.08)', accent: C.blue },
  warn: { border: 'rgba(245,166,35,0.35)', bg: 'rgba(245,166,35,0.08)', accent: C.amb },
  danger: { border: '#4a1d1d', bg: 'rgba(255,77,79,0.08)', accent: C.red },
  ok: { border: 'rgba(12,206,107,0.30)', bg: 'rgba(12,206,107,0.07)', accent: C.grn },
};

/**
 * The one thing the founder most needs to act on, at the top of the dashboard.
 *
 * Priority: email → expired trial → optional registration docs → trial countdown.
 * Company verification no longer hard-locks the product (no server status yet).
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

  if (!account.emailVerified) {
    const copy = gateCopy('email', 'founder');
    return (
      <Banner
        tone="warn"
        eyebrow="CONFIRM YOUR EMAIL"
        title={copy.title}
        body={copy.body}
        cta={copy.cta}
        onPress={onConfirmEmail}
      />
    );
  }

  if (locked) {
    const copy = gateCopy('payment', 'founder');
    return (
      <Banner
        tone="danger"
        eyebrow="TRIAL ENDED"
        title={copy.title}
        body={`${copy.body} Your ${TRIAL_DAYS}-day trial has finished.`}
        cta={copy.cta}
        onPress={onUnlock}
      />
    );
  }

  if (!account.registration) {
    const copy = gateCopy('verification', 'founder');
    return (
      <Banner
        tone="info"
        eyebrow={`TRIAL · ${days} ${days === 1 ? 'DAY' : 'DAYS'} LEFT`}
        title={copy.title}
        body={`${copy.body} Store your certificate so audits can cite a real entity.`}
        cta={copy.cta}
        onPress={onVerify}
      />
    );
  }

  if (isPaid(account)) return null;

  return (
    <Banner
      tone="ok"
      eyebrow={`TRIAL · ${days} ${days === 1 ? 'DAY' : 'DAYS'} LEFT`}
      title="Clear readiness tasks, then publish"
      body="When required tasks pass, publish from Home to appear in investor dealflow."
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
      <Txt className="text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
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
