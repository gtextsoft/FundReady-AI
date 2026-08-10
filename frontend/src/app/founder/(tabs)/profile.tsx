import { useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Eyebrow, Mono, Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { Unavailable } from '@/components/unavailable';
import { C } from '@/theme/tokens';
import { api } from '@/api';
import { daysLeftInTrial, hasAccess, isPaid } from '@/domain/access';
import { UNLOCK_PRICE } from '@/domain/pricing';
import { initials } from '@/lib/format';
import type { VerificationStatus } from '@/domain/types';
import { route, SIGN_IN, VERIFY_EMAIL } from '@/lib/routes';
import { isAssessmentComplete, useFounder } from '@/store/founder';
import { useSession } from '@/store/session';

const VERIFICATION_COPY: Record<VerificationStatus, { label: string; color: string }> = {
  unverified: { label: 'Not verified', color: C.amb },
  in_review: { label: 'In review', color: C.blue },
  verified: { label: 'Verified', color: C.grn },
  rejected: { label: 'Rejected', color: C.red },
};

export default function FounderProfile() {
  const insets = useSafeAreaInsets();
  const session = useSession((s) => s.session);
  const account = useSession((s) => s.founderAccount);
  const signOut = useSession((s) => s.signOut);
  const resetFounder = useFounder((s) => s.reset);
  const profile = useFounder((s) => s.profile);
  const report = useFounder((s) => s.report);
  const run = useFounder((s) => s.run);

  const [busy, setBusy] = useState(false);
  const [resetSent, setResetSent] = useState(false);
  const [resetError, setResetError] = useState<unknown>(null);

  const email = session?.email ?? '';

  /**
   * Password changes go through the email reset, because that is the only
   * mechanism the API has — there is no authenticated change-password
   * endpoint. That is not a workaround: proving control of the mailbox before
   * changing the credential is why a stolen session cannot take an account
   * over, and completing it revokes every refresh token.
   */
  async function changePassword() {
    if (!email) return;
    setBusy(true);
    setResetError(null);
    try {
      await api.requestPasswordReset(email);
      setResetSent(true);
    } catch (e) {
      setResetError(e);
    } finally {
      setBusy(false);
    }
  }

  if (!account) return <View className="flex-1 bg-ground" />;

  const verification = VERIFICATION_COPY[account.verification];
  const locked = !hasAccess(account);
  const paid = isPaid(account);
  const assessed = report !== null || run !== null || isAssessmentComplete(profile);

  const goVerifyEmail = () => router.push(VERIFY_EMAIL);

  async function out() {
    await signOut();
    resetFounder();
    router.replace(SIGN_IN);
  }

  return (
    <ScrollView
      className="flex-1 bg-ground"
      contentContainerStyle={{ paddingTop: insets.top + 8, paddingHorizontal: 18, paddingBottom: 24 }}
      showsVerticalScrollIndicator={false}>
      <TxtSemi className="mb-4 text-[19px]" style={{ letterSpacing: -0.5 }}>
        Profile
      </TxtSemi>

      <View className="flex-row items-center gap-3 rounded-[12px] border border-line bg-surface-1 p-[14px]">
        <View className="h-[44px] w-[44px] items-center justify-center rounded-full border border-line-strong bg-surface-3">
          <TxtSemi className="text-[14px] text-ink-muted">
            {session?.displayName ? initials(session.displayName) : 'F'}
          </TxtSemi>
        </View>
        <View className="flex-1">
          {/* The person first — this is their profile, not the company's. */}
          <TxtSemi className="text-[15px]">{session?.displayName ?? 'Your profile'}</TxtSemi>
          <Txt className="text-[12px] text-ink-muted">
            {profile.company || account.companyName || 'Your company'}
          </Txt>
          <Txt className="text-[12px] text-ink-dim">{session?.email ?? 'not signed in'}</Txt>
        </View>
        <View className="rounded-[5px] border border-line-strong px-2 py-[3px]">
          <Mono className="text-[9.5px]" style={{ color: C.inkMuted }}>
            FOUNDER
          </Mono>
        </View>
      </View>

      {/* account */}
      <Eyebrow className="mb-[10px] mt-6">ACCOUNT</Eyebrow>
      <View className="rounded-[12px] border border-line bg-surface-1">
        <Row
          label="Email address"
          value={session?.email ?? '—'}
          status={
            account.emailVerified
              ? { text: 'CONFIRMED', color: C.grn }
              : { text: 'UNCONFIRMED', color: C.amb }
          }
          // Unconfirmed is not cosmetic: the server refuses every profile,
          // audit and discovery route until it is done.
          action={account.emailVerified ? undefined : { label: 'Confirm', onPress: goVerifyEmail }}
        />
        <Divider />
        <Row label="Name" value={session?.displayName || '—'} />
        <Divider />
        <Row label="Role" value="Founder" />
      </View>

      {/* security */}
      <Eyebrow className="mb-[10px] mt-6">SECURITY</Eyebrow>
      <View className="rounded-[12px] border border-line bg-surface-1">
        <Row
          label="Password"
          value={
            resetSent
              ? 'Reset link sent — check your inbox'
              : 'Changed by email, so a stolen session cannot do it'
          }
          action={
            resetSent
              ? undefined
              : { label: busy ? 'Sending…' : 'Change', onPress: () => void changePassword() }
          }
        />
        <Divider />
        {/* Honest about the limit rather than showing a toggle that lies:
            `/v1/users/me` carries no MFA field, so the app cannot tell whether
            two-factor is already on, and a switch defaulting to "off" would
            claim something it does not know. */}
        <Row
          label="Two-factor authentication"
          value="Not available in the app yet"
          status={{ text: 'SOON', color: C.inkFaint }}
        />
      </View>

      {resetError ? (
        <Unavailable title="Could not start the password change" error={resetError} className="mt-3" />
      ) : null}

      {resetSent ? (
        <Txt className="mt-3 text-[12px] text-ink-faint" style={{ lineHeight: 18 }}>
          Completing the reset signs you out on every device, including this one.
        </Txt>
      ) : null}

      {/* assessment */}
      <Eyebrow className="mb-[10px] mt-6">ASSESSMENT</Eyebrow>
      <Pressable
        accessibilityRole="button"
        onPress={() => router.push(route(assessed ? '/results' : '/onboarding'))}
        className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
        <View className="flex-row items-center justify-between">
          <TxtMed className="text-[13.5px]">{assessed ? 'Your latest result' : 'Not taken yet'}</TxtMed>
          <Txt className="text-[13px] text-ink-faint">›</Txt>
        </View>
        <Txt className="mt-2 text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
          {assessed
            ? 'Your score, what does not add up, and what to do next.'
            : 'Four short steps. Investors cannot see you without a score.'}
        </Txt>
      </Pressable>

      {/* verification */}
      <Eyebrow className="mb-[10px] mt-6">COMPANY VERIFICATION</Eyebrow>
      <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
        <View className="flex-row items-center justify-between">
          <TxtMed className="text-[13.5px]">Registration status</TxtMed>
          <View className="flex-row items-center gap-2">
            <View className="h-[6px] w-[6px] rounded-full" style={{ backgroundColor: verification.color }} />
            <Mono className="text-[11px]" style={{ color: verification.color }}>
              {verification.label}
            </Mono>
          </View>
        </View>
        {account.registration ? (
          <Txt className="mt-2 text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
            {account.registration.legalName} · {account.registration.registrationNumber} ·{' '}
            {account.registration.country}
          </Txt>
        ) : (
          <Txt className="mt-2 text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
            Confirm your company is registered in your country to be seen by investors.
          </Txt>
        )}
        {account.verification !== 'verified' && account.verification !== 'in_review' ? (
          <View className="mt-3">
            <Button label="Verify company" height={42} onPress={() => router.push(route('/founder/verify'))} />
          </View>
        ) : null}
      </View>

      {/* access */}
      <Eyebrow className="mb-[10px] mt-6">ACCESS</Eyebrow>
      <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
        <View className="flex-row items-center justify-between">
          <TxtMed className="text-[13.5px]">
            {paid ? 'Unlocked' : locked ? 'Trial ended' : 'Free trial'}
          </TxtMed>
          <Mono className="text-[11px]" style={{ color: paid ? C.grn : locked ? C.red : C.amb }}>
            {paid
              ? `${UNLOCK_PRICE.label} PAID`
              : locked
                ? 'LOCKED'
                : `${daysLeftInTrial(account)} DAYS LEFT`}
          </Mono>
        </View>
        <Txt className="mt-2 text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
          {paid
            ? 'One-off payment received. Your access does not expire.'
            : 'Full access during the trial. A single one-off payment keeps it permanently.'}
        </Txt>
        {!paid ? (
          <View className="mt-3">
            <Button
              label={`Unlock for ${UNLOCK_PRICE.label}`}
              height={42}
              onPress={() => router.push(route('/founder/paywall'))}
            />
          </View>
        ) : null}
      </View>

      <View className="mt-6">
        <Button label="Sign out" variant="secondary" onPress={out} />
      </View>
    </ScrollView>
  );
}

/** One labelled line in a settings group, with an optional badge and action. */
function Row({
  label,
  value,
  status,
  action,
}: {
  label: string;
  value: string;
  status?: { text: string; color: string };
  action?: { label: string; onPress: () => void };
}) {
  return (
    <View className="p-[14px]">
      <View className="flex-row items-center justify-between gap-3">
        <TxtMed className="text-[13.5px]">{label}</TxtMed>
        <View className="flex-row items-center gap-2">
          {status ? (
            <>
              <View className="h-[6px] w-[6px] rounded-full" style={{ backgroundColor: status.color }} />
              <Mono className="text-[10.5px]" style={{ color: status.color }}>
                {status.text}
              </Mono>
            </>
          ) : null}
          {/* Not nested inside the row's own pressable — two Pressables one
              inside the other render as nested <button> on web, which React
              refuses to hydrate (AGENTS.md, trap 5). */}
          {action ? (
            <Pressable accessibilityRole="button" onPress={action.onPress} hitSlop={8}>
              <TxtMed className="text-[12.5px]" style={{ color: C.blue }}>
                {action.label}
              </TxtMed>
            </Pressable>
          ) : null}
        </View>
      </View>
      <Txt className="mt-[5px] text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
        {value}
      </Txt>
    </View>
  );
}

function Divider() {
  return <View className="h-px" style={{ backgroundColor: C.line }} />;
}
