import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Mark } from '@/components/ui/mark';
import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { Unavailable } from '@/components/unavailable';
import { C } from '@/theme/tokens';
import { api, RESEND_COOLDOWN_MS } from '@/api';
import { isValidEmail } from '@/domain/email';
import { homeFor, ONBOARDING, SIGN_IN } from '@/lib/routes';
import { useSession } from '@/store/session';

/**
 * Confirm the address on the account with the six-digit code from the email.
 *
 * The *state* here is real: `emailVerified` comes from the server's own
 * `email_verified` on every load, so the moment the backend marks an address
 * confirmed this screen agrees.
 *
 * **The email carries a code, not a link.** There is deliberately no deep-link
 * handling left here: a link would have to be a credential in a URL, and the
 * server now checks a code against one named account instead. `reset-password`
 * still uses a token link, which is why `lib/deep-link.ts` remains.
 *
 * **Usable signed out.** Neither endpoint is authenticated, because someone who
 * registered on a laptop may be reading the mail on a phone. Signed in, the
 * address comes off the session; signed out, the screen asks for it, because
 * the server needs it to know which account the code belongs to.
 *
 * Deliberately skippable. AUTH.md permits browsing your own empty account
 * while unverified -- it is the sensitive actions that are gated, and
 * `domain/access.ts` is what enforces that.
 */
export default function VerifyEmail() {
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ next?: string }>();

  /**
   * Where to go once confirmed, and whether this screen may be skipped.
   *
   * Registration sends `?next=onboarding` (or `investor`). Arriving that way
   * makes verification compulsory: there is no "skip", because everything on
   * the other side of this screen is refused by the server until the address
   * is confirmed. Reached from the dashboard instead, there is no `next` and
   * the screen stays skippable — AUTH.md allows browsing your own empty
   * account while unverified.
   */
  const next = params.next;
  const required = next !== undefined;

  const session = useSession((s) => s.session);
  const role = useSession((s) => s.role);
  const founderAccount = useSession((s) => s.founderAccount);
  const investorAccount = useSession((s) => s.investorAccount);
  const refreshAccount = useSession((s) => s.refreshAccount);
  const signOut = useSession((s) => s.signOut);

  const account = role === 'investor' ? investorAccount : founderAccount;

  // Signed in, the address is known and must not be editable — a code is only
  // ever checked against the account it was issued for, so letting someone
  // type a different address here would only produce confusing failures.
  const sessionEmail = session?.email ?? '';
  const [typedEmail, setTypedEmail] = useState('');
  const email = sessionEmail || typedEmail;

  const [code, setCode] = useState('');
  const [busy, setBusy] = useState<'resend' | 'confirm' | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [checking, setChecking] = useState(false);
  const [sentAt, setSentAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  /**
   * Set when *this screen* completed the confirmation. Needed on top of the
   * server state because someone verifying while signed out has no account to
   * re-read — without it, a success would still render "pending".
   */
  const [confirmedHere, setConfirmedHere] = useState(false);

  const verified = confirmedHere || (account?.emailVerified ?? false);

  // `next=onboarding` continues into the assessment, which is where a founder
  // was heading before this screen existed. Anything else falls back to their
  // own side of the marketplace.
  const onward = next === 'onboarding' ? ONBOARDING : homeFor(role);
  const onwardLabel = next === 'onboarding' ? 'Start your assessment' : 'Continue';

  // The server drops a resend made within 60s of the last one and still
  // answers 202, so the countdown is the only thing that stops the button
  // promising an email that was never dispatched.
  const cooldownLeft = sentAt === null ? 0 : Math.max(0, sentAt + RESEND_COOLDOWN_MS - now);
  const cooldownSeconds = Math.ceil(cooldownLeft / 1000);

  useEffect(() => {
    if (cooldownLeft <= 0) return;
    const id = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(id);
  }, [cooldownLeft]);

  const digits = code.replace(/[\s-]/g, '');
  const canConfirm = digits.length > 0 && isValidEmail(email);

  async function confirm() {
    if (!canConfirm) return;
    setBusy('confirm');
    setError(null);
    try {
      await api.confirmEmail(email, code);
      setConfirmedHere(true);
      // Best effort: signed out there is no account to re-read, and the
      // confirmation has already succeeded either way.
      await refreshAccount().catch(() => undefined);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  async function resend() {
    if (!isValidEmail(email) || cooldownLeft > 0) return;
    setBusy('resend');
    setError(null);
    try {
      await api.resendVerificationEmail(email);
      // Start the countdown on the attempt, not on a confirmation: the 202
      // says nothing about whether a message went out.
      setSentAt(Date.now());
      setNow(Date.now());
      setCode('');
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  /** Re-reads the server, so a confirmation completed elsewhere lands here. */
  async function recheck() {
    setChecking(true);
    setError(null);
    try {
      await refreshAccount();
    } catch (e) {
      setError(e);
    } finally {
      setChecking(false);
    }
  }

  return (
    <KeyboardAvoidingView
      className="flex-1 bg-ground"
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView
        contentContainerStyle={{
          flexGrow: 1,
          paddingTop: insets.top + 8,
          paddingHorizontal: 26,
          paddingBottom: insets.bottom + 34,
        }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}>
        <View className="flex-1 justify-center py-7">
          <Mark size={38} />

          <TxtSemi className="mb-3 mt-7 text-[30px]" style={{ letterSpacing: -1.1, lineHeight: 33 }}>
            {verified ? 'Your email is confirmed.' : 'Confirm your email.'}
          </TxtSemi>

          {/* Real server state, re-read on every load. */}
          <View
            className="mb-6 flex-row items-center gap-2 self-start rounded-[7px] px-[9px] py-[6px]"
            style={{
              borderWidth: 1,
              borderColor: verified ? 'rgba(12,206,107,0.30)' : 'rgba(245,166,35,0.35)',
              backgroundColor: verified ? 'rgba(12,206,107,0.07)' : 'rgba(245,166,35,0.08)',
            }}>
            <View
              className="h-[6px] w-[6px] rounded-full"
              style={{ backgroundColor: verified ? C.grn : C.amb }}
            />
            <Mono
              className="text-[10px]"
              style={{ letterSpacing: 1, color: verified ? C.grn : C.amb }}>
              {verified ? 'VERIFIED' : 'PENDING VERIFICATION'}
            </Mono>
          </View>

          <Txt className="mb-6 text-[13px] text-ink-muted" style={{ lineHeight: 20 }}>
            {verified
              ? `${email || 'Your address'} is confirmed. Everything that needs a confirmed address is now open to you.`
              : `Enter the six-digit code we emailed${sessionEmail ? ` to ${sessionEmail}` : ''}. You can look around your own account in the meantime.`}
          </Txt>

          {!verified ? (
            <>
              <View className="gap-[14px]">
                {/* Signed out, the server has no way to know which account the
                    code belongs to, so the address has to come from here. */}
                {sessionEmail ? null : (
                  <Field
                    label="Email address"
                    placeholder="you@company.com"
                    value={typedEmail}
                    onChangeText={(v) => {
                      setTypedEmail(v);
                      if (error) setError(null);
                    }}
                    autoCapitalize="none"
                    autoComplete="email"
                    keyboardType="email-address"
                  />
                )}

                <Field
                  label="Verification code"
                  placeholder="123456"
                  value={code}
                  onChangeText={(v) => {
                    setCode(v);
                    if (error) setError(null);
                  }}
                  // Not `number-pad`: a code pasted from an email arrives with
                  // spaces, and the server ignores them anyway.
                  keyboardType="numbers-and-punctuation"
                  autoCapitalize="none"
                  autoComplete="one-time-code"
                  textContentType="oneTimeCode"
                  mono
                  onSubmitEditing={confirm}
                  hint="Six digits, from the email. It expires shortly after it is sent."
                />
              </View>

              <View className="mt-[18px] gap-[10px]">
                <Button
                  label="Confirm email"
                  loading={busy === 'confirm'}
                  disabled={!canConfirm}
                  onPress={confirm}
                />
                <Button
                  label={
                    cooldownLeft > 0 ? `Send a new code in ${cooldownSeconds}s` : 'Send a new code'
                  }
                  variant="secondary"
                  loading={busy === 'resend'}
                  disabled={cooldownLeft > 0 || !isValidEmail(email)}
                  onPress={resend}
                />
                {session ? (
                  <Button
                    label="I've confirmed — check again"
                    variant="secondary"
                    loading={checking}
                    onPress={recheck}
                  />
                ) : null}
              </View>

              {/* Deliberately does not claim a message was sent: the endpoint
                  answers the same whether or not one was. */}
              {sentAt !== null && !error ? (
                <Txt className="mt-4 text-[12px] text-ink-faint" style={{ lineHeight: 18 }}>
                  If that address needs verifying, a new code is on its way and any earlier one has
                  stopped working.
                </Txt>
              ) : null}
            </>
          ) : (
            <Button
              label={session ? onwardLabel : 'Sign in'}
              onPress={() => router.replace(session ? onward : SIGN_IN)}
            />
          )}

          {/* A wrong code, an expired one, one already used and one whose
              attempts are exhausted all fail identically, so the title must not
              claim to know which it was. */}
          {error ? (
            <Unavailable title="That code did not work" error={error} className="mt-5" />
          ) : null}

          {/* No way past this screen when it is required: everything on the
              other side of it is refused by the server until the address is
              confirmed, so "skip" would only lead somewhere that does not
              work. Signing out stays available. */}
          {!verified && !required ? (
            <Pressable
              accessibilityRole="link"
              className="mt-6 items-center"
              onPress={() => router.replace(session ? homeFor(role) : SIGN_IN)}>
              <Txt className="text-[12.5px] text-ink-muted">
                {session ? 'Skip for now' : 'Back to sign in'}
              </Txt>
            </Pressable>
          ) : null}

          {!verified && required ? (
            <Pressable
              accessibilityRole="link"
              className="mt-6 items-center"
              onPress={() => void signOut()}>
              <Txt className="text-[12.5px] text-ink-muted">Use a different account</Txt>
            </Pressable>
          ) : null}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
