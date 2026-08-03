import { useEffect, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Mark } from '@/components/ui/mark';
import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { Unavailable } from '@/components/unavailable';
import { C } from '@/theme/tokens';
import { api } from '@/api';
import { tokenFromParams } from '@/lib/deep-link';
import { homeFor, SIGN_IN } from '@/lib/routes';
import { useSession } from '@/store/session';

/**
 * Confirm the address on the account.
 *
 * The *state* here is real: `emailVerified` comes from the server's own
 * `email_verified` on every load, so the moment the backend marks an address
 * confirmed this screen agrees.
 *
 * Two ways in. Normally the account is signed in and lands here from the
 * dashboard. But the verification email points at
 * `{APP_LINK_BASE_URL}/verify-email?token=…`, so this screen is also the far
 * end of that link — and whoever follows it may well not be signed in on this
 * device. The confirm endpoint takes no authorization for exactly that reason,
 * so the token is submitted regardless and the session is only used to *show*
 * the result.
 *
 * Deliberately skippable. AUTH.md permits browsing your own empty account
 * while unverified -- it is the sensitive actions that are gated, and
 * `domain/access.ts` is what enforces that.
 */
export default function VerifyEmail() {
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams();

  const session = useSession((s) => s.session);
  const role = useSession((s) => s.role);
  const founderAccount = useSession((s) => s.founderAccount);
  const investorAccount = useSession((s) => s.investorAccount);
  const refreshAccount = useSession((s) => s.refreshAccount);

  const account = role === 'investor' ? investorAccount : founderAccount;

  const [token, setToken] = useState('');
  const [busy, setBusy] = useState<'resend' | 'confirm' | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [checking, setChecking] = useState(false);
  /**
   * Set when *this screen* completed the confirmation. Needed on top of the
   * server state because a link followed while signed out has no account to
   * re-read — without it, a successful confirmation would still render
   * "pending".
   */
  const [confirmedHere, setConfirmedHere] = useState(false);

  const verified = confirmedHere || (account?.emailVerified ?? false);

  const linked = tokenFromParams(params);

  async function confirmWith(value: string) {
    const trimmed = value.trim();
    if (!trimmed) return;
    setBusy('confirm');
    setError(null);
    try {
      await api.confirmEmail(trimmed);
      setConfirmedHere(true);
      // Best effort: signed out, there is no account to re-read, and the
      // confirmation has already succeeded either way.
      await refreshAccount().catch(() => undefined);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  /**
   * A token on the URL is submitted on arrival rather than shown in a box —
   * the person already clicked the link, and asking them to press Confirm
   * afterwards is a step that exists only because the code was not read.
   *
   * The ref guard is what keeps it to one attempt. Without it a re-render (or
   * the React Compiler re-running this) would spend the token again, and the
   * second attempt fails: these are single-use.
   */
  const attempted = useRef(false);
  useEffect(() => {
    if (!linked || attempted.current) return;
    attempted.current = true;
    void confirmWith(linked);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linked]);

  async function resend() {
    setBusy('resend');
    setError(null);
    try {
      await api.resendVerificationEmail();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  const confirm = () => confirmWith(token);

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
    <KeyboardAvoidingView className="flex-1 bg-ground" behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
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
            <Mono className="text-[10px]" style={{ letterSpacing: 1, color: verified ? C.grn : C.amb }}>
              {verified ? 'VERIFIED' : 'PENDING VERIFICATION'}
            </Mono>
          </View>

          <Txt className="mb-6 text-[13px] text-ink-muted" style={{ lineHeight: 20 }}>
            {verified
              ? `${session?.email ?? 'Your address'} is confirmed. Everything that needs a confirmed address is now open to you.`
              : `We need to know you control ${session?.email ?? 'this address'} before you can be discovered by investors, upload documents, or pay for anything. You can look around your own account in the meantime.`}
          </Txt>

          {!verified ? (
            <>
              {/* The link carried the token, so there is nothing to type —
                  show the attempt, not an input someone has to re-fill. */}
              {linked && busy === 'confirm' ? (
                <View className="rounded-[11px] border border-line bg-surface-1 p-4">
                  <Txt className="text-[12.5px] text-ink-muted">
                    Confirming your address…
                  </Txt>
                </View>
              ) : (
                <>
                  {linked ? null : (
                    <Field
                      label="Confirmation code"
                      placeholder="Paste the code from your email"
                      value={token}
                      onChangeText={setToken}
                      autoCapitalize="none"
                    />
                  )}

                  <View className="mt-[18px] gap-[10px]">
                    {linked ? (
                      <Button
                        label="Try again"
                        loading={busy === 'confirm'}
                        onPress={() => confirmWith(linked)}
                      />
                    ) : (
                      <Button
                        label="Confirm email"
                        loading={busy === 'confirm'}
                        disabled={!token.trim()}
                        onPress={confirm}
                      />
                    )}
                    {/* Both of these act on the signed-in account, so they are
                        meaningless to someone who followed the link on a
                        device that is signed out. */}
                    {session ? (
                      <>
                        <Button
                          label="Resend the email"
                          variant="secondary"
                          loading={busy === 'resend'}
                          onPress={resend}
                        />
                        <Button
                          label="I've confirmed — check again"
                          variant="secondary"
                          loading={checking}
                          onPress={recheck}
                        />
                      </>
                    ) : null}
                  </View>
                </>
              )}
            </>
          ) : (
            <Button
              label={session ? 'Continue' : 'Sign in'}
              onPress={() => router.replace(session ? homeFor(role) : SIGN_IN)}
            />
          )}

          {/* Unknown, expired and already-used tokens are one message by
              design, so the title must not claim to know which it was. */}
          {error ? (
            <Unavailable title="That link did not work" error={error} className="mt-5" />
          ) : null}

          {!verified ? (
            <Pressable
              accessibilityRole="link"
              className="mt-6 items-center"
              onPress={() => router.replace(session ? homeFor(role) : SIGN_IN)}>
              <Txt className="text-[12.5px] text-ink-muted">
                {session ? 'Skip for now' : 'Back to sign in'}
              </Txt>
            </Pressable>
          ) : null}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
