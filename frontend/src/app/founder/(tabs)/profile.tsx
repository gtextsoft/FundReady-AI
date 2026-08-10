import { useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppearanceControl } from '@/components/appearance-control';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Eyebrow, Mono, Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { Unavailable } from '@/components/unavailable';
import { C } from '@/theme/tokens';
import { useThemeColors } from '@/theme/use-theme-colors';
import { api } from '@/api';
import { daysLeftInTrial, hasAccess, isPaid } from '@/domain/access';
import { UNLOCK_PRICE } from '@/domain/pricing';
import { initials } from '@/lib/format';
import { RESET_PASSWORD, route, SIGN_IN, VERIFY_EMAIL } from '@/lib/routes';
import { isAssessmentComplete, useFounder } from '@/store/founder';
import { useSession } from '@/store/session';

export default function FounderProfile() {
  const insets = useSafeAreaInsets();
  const colors = useThemeColors();
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
  const [mfaSecret, setMfaSecret] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState('');
  const [mfaCodes, setMfaCodes] = useState<string[] | null>(null);
  const [mfaError, setMfaError] = useState<string | null>(null);
  const [mfaBusy, setMfaBusy] = useState(false);

  const email = session?.email ?? '';

  /**
   * Password changes go through the emailed reset code, because that is the
   * only mechanism the API has — there is no authenticated change-password
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
      router.push(route(`${RESET_PASSWORD}?email=${encodeURIComponent(email)}`));
    } catch (e) {
      setResetError(e);
    } finally {
      setBusy(false);
    }
  }

  if (!account) return <View className="flex-1 bg-ground" />;

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
          <Mono className="text-[9.5px]" style={{ color: colors.inkMuted }}>
            FOUNDER
          </Mono>
        </View>
      </View>

      <View className="mt-6 rounded-[12px] border border-line bg-surface-1 p-[14px]">
        <AppearanceControl />
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
              ? 'Reset code sent — enter it to finish'
              : 'Changed by email code, so a stolen session cannot do it'
          }
          action={
            resetSent
              ? undefined
              : { label: busy ? 'Sending…' : 'Change', onPress: () => void changePassword() }
          }
        />
        <Divider />
        <View className="px-[14px] py-3">
          <TxtMed className="text-[13.5px]">Two-factor authentication</TxtMed>
          {mfaCodes ? (
            <View className="mt-2 gap-1">
              <Txt className="text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
                MFA is on. Store these recovery codes now — they will not be shown again.
              </Txt>
              {mfaCodes.map((c) => (
                <Mono key={c} className="text-[12px]">
                  {c}
                </Mono>
              ))}
            </View>
          ) : mfaSecret ? (
            <View className="mt-2 gap-2">
              <Txt className="text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
                Add this secret to your authenticator app, then enter a 6-digit code.
              </Txt>
              <Mono className="text-[11px] text-ink">{mfaSecret}</Mono>
              <Field
                label="Authenticator code"
                value={mfaCode}
                onChangeText={setMfaCode}
                keyboardType="number-pad"
                mono
              />
              <Button
                label={mfaBusy ? 'Confirming…' : 'Confirm MFA'}
                height={40}
                loading={mfaBusy}
                onPress={async () => {
                  setMfaBusy(true);
                  setMfaError(null);
                  try {
                    setMfaCodes(await api.confirmMfaEnrolment(mfaCode));
                    setMfaSecret(null);
                  } catch (e) {
                    setMfaError(e instanceof Error ? e.message : 'Could not confirm MFA.');
                  } finally {
                    setMfaBusy(false);
                  }
                }}
              />
            </View>
          ) : (
            <View className="mt-2">
              <Txt className="mb-2 text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
                Optional. The app cannot tell if MFA is already on — enrolling again replaces an
                unfinished setup.
              </Txt>
              <Button
                label={mfaBusy ? 'Starting…' : 'Enable MFA'}
                height={40}
                variant="secondary"
                loading={mfaBusy}
                onPress={async () => {
                  setMfaBusy(true);
                  setMfaError(null);
                  try {
                    const enrolment = await api.beginMfaEnrolment();
                    setMfaSecret(enrolment.secret);
                  } catch (e) {
                    setMfaError(e instanceof Error ? e.message : 'Could not start MFA.');
                  } finally {
                    setMfaBusy(false);
                  }
                }}
              />
            </View>
          )}
          {mfaError ? (
            <Txt className="mt-2 text-[12px]" style={{ color: C.red }}>
              {mfaError}
            </Txt>
          ) : null}
        </View>
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
            : 'Five short steps. Investors cannot see you without a score.'}
        </Txt>
      </Pressable>

      {/* registration docs */}
      <Eyebrow className="mb-[10px] mt-6">COMPANY REGISTRATION</Eyebrow>
      <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
        <TxtMed className="text-[13.5px]">Legal details & certificate</TxtMed>
        {account.registration ? (
          <Txt className="mt-2 text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
            {account.registration.legalName} · {account.registration.registrationNumber} ·{' '}
            {account.registration.country}
          </Txt>
        ) : (
          <Txt className="mt-2 text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
            Optional: store registration for audits. Publishing uses the readiness gate on Home.
          </Txt>
        )}
        <View className="mt-3">
          <Button
            label={account.registration ? 'Update registration' : 'Add registration'}
            height={42}
            variant="secondary"
            onPress={() => router.push(route('/founder/verify'))}
          />
        </View>
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
