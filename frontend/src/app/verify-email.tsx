import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Mark } from '@/components/ui/mark';
import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { Unavailable } from '@/components/unavailable';
import { C } from '@/theme/tokens';
import { api } from '@/api';
import { homeFor } from '@/lib/routes';
import { useSession } from '@/store/session';

/**
 * Confirm the address on the account.
 *
 * The *state* here is real: `emailVerified` comes from the server's own
 * `email_verified` on every load, so the moment the backend marks an address
 * confirmed this screen agrees. The two actions are not built yet (T1.2b), so
 * they say so instead of pretending a message went out.
 *
 * Deliberately skippable. AUTH.md permits browsing your own empty account
 * while unverified -- it is the sensitive actions that are gated, and
 * `domain/access.ts` is what enforces that.
 */
export default function VerifyEmail() {
  const insets = useSafeAreaInsets();

  const session = useSession((s) => s.session);
  const role = useSession((s) => s.role);
  const founderAccount = useSession((s) => s.founderAccount);
  const investorAccount = useSession((s) => s.investorAccount);
  const refreshAccount = useSession((s) => s.refreshAccount);

  const account = role === 'investor' ? investorAccount : founderAccount;
  const verified = account?.emailVerified ?? false;

  const [token, setToken] = useState('');
  const [busy, setBusy] = useState<'resend' | 'confirm' | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [checking, setChecking] = useState(false);

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

  async function confirm() {
    if (!token.trim()) return;
    setBusy('confirm');
    setError(null);
    try {
      await api.confirmEmail(token.trim());
      await refreshAccount();
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
              <Field
                label="Confirmation code"
                placeholder="Paste the code from your email"
                value={token}
                onChangeText={setToken}
                autoCapitalize="none"
              />

              <View className="mt-[18px] gap-[10px]">
                <Button
                  label="Confirm email"
                  loading={busy === 'confirm'}
                  disabled={!token.trim()}
                  onPress={confirm}
                />
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
              </View>
            </>
          ) : (
            <Button label="Continue" onPress={() => router.replace(homeFor(role))} />
          )}

          {error ? <Unavailable title="Email verification is not live" error={error} className="mt-5" /> : null}

          {!verified ? (
            <Pressable
              accessibilityRole="link"
              className="mt-6 items-center"
              onPress={() => router.replace(homeFor(role))}>
              <Txt className="text-[12.5px] text-ink-muted">Skip for now</Txt>
            </Pressable>
          ) : null}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
