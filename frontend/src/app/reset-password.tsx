import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Mark } from '@/components/ui/mark';
import { Mono, Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { Unavailable } from '@/components/unavailable';
import { C } from '@/theme/tokens';
import { api, ApiFailure } from '@/api';
import { checkPassword, PASSWORD_HINT } from '@/domain/password';
import { tokenFromParams } from '@/lib/deep-link';
import { FORGOT_PASSWORD, SIGN_IN } from '@/lib/routes';

/**
 * The far end of the reset the email started.
 *
 * Reached from `{APP_LINK_BASE_URL}/reset-password?token=…`, so the token
 * arrives as a search parameter and the field for it never has to be shown.
 * The paste box is the fallback for when the link opened a browser instead of
 * the app — which is what happens today, because Universal/App Links are not
 * configured yet (see `lib/deep-link.ts`).
 *
 * **Deliberately usable while signed out.** The endpoint takes no
 * authorization, and someone resetting a password is very often locked out of
 * the account — requiring a session here would close the only door they have.
 */
export default function ResetPassword() {
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams();

  // The token from the link. Held in state so a bad one can be replaced by
  // hand without needing another email.
  const linked = tokenFromParams(params);
  const [token, setToken] = useState(linked ?? '');
  const [email, setEmail] = useState(typeof params.email === 'string' ? params.email : '');

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState(false);

  async function submit() {
    const check = checkPassword(password, confirm);
    if (!check.ok) {
      setFieldError(check.message);
      return;
    }
    if (!confirm) {
      setFieldError('Type your new password twice.');
      return;
    }
    if (!email.trim()) {
      setFieldError('Enter the email address you reset.');
      return;
    }
    if (!token.trim()) {
      setFieldError('Paste the code from your reset email.');
      return;
    }

    setBusy(true);
    setFieldError(null);
    setError(null);
    try {
      await api.resetPassword(email.trim(), token.trim(), password);
      setDone(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  // Unknown, expired and already-used tokens are one indistinguishable
  // failure by design, so the offer is always the same: get a fresh link.
  const badToken = error instanceof ApiFailure && error.code === 'validation';

  return (
    <KeyboardAvoidingView
      className="flex-1 bg-obsidian"
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

          <TxtSemi
            className="mb-3 mt-7 text-[30px]"
            style={{ letterSpacing: -1.1, lineHeight: 33 }}>
            {done ? 'Password changed.' : 'Choose a new password.'}
          </TxtSemi>

          {done ? (
            <>
              <View className="mb-6 rounded-[11px] border border-graphite bg-carbon-low p-4">
                <View className="mb-2 flex-row items-center gap-2">
                  <View
                    className="h-[6px] w-[6px] rounded-full"
                    style={{ backgroundColor: C.signal }}
                  />
                  <Mono className="text-[10px]" style={{ letterSpacing: 1, color: C.signal }}>
                    SIGNED OUT EVERYWHERE
                  </Mono>
                </View>
                {/* Said plainly, because otherwise the other device looking
                    signed out reads as a fault rather than as the point. */}
                <Txt className="text-[12.5px] text-bone-secondary" style={{ lineHeight: 19 }}>
                  Every device signed in to this account has been signed out, including any
                  that were not yours. Sign in again with your new password.
                </Txt>
              </View>
              <Button label="Sign in" onPress={() => router.replace(SIGN_IN)} />
            </>
          ) : (
            <>
              <Txt className="mb-6 text-[13px] text-bone-secondary" style={{ lineHeight: 20 }}>
                {linked
                  ? 'Your reset link checked out. Pick a new password and every other device will be signed out.'
                  : 'Paste the code from your reset email, then pick a new password.'}
              </Txt>

              <View className="gap-[14px]">
                <Field
                  label="Email"
                  placeholder="you@company.com"
                  value={email}
                  onChangeText={(value) => {
                    setEmail(value);
                    if (fieldError) setFieldError(null);
                  }}
                  autoCapitalize="none"
                  autoComplete="email"
                  keyboardType="email-address"
                />
                {linked ? null : (
                  <Field
                    label="Reset code"
                    placeholder="Paste the code from your email"
                    value={token}
                    onChangeText={(value) => {
                      setToken(value);
                      if (error) setError(null);
                    }}
                    autoCapitalize="none"
                  />
                )}

                <Field
                  label="New password"
                  placeholder="At least 12 characters"
                  value={password}
                  onChangeText={(value) => {
                    setPassword(value);
                    if (fieldError) setFieldError(null);
                  }}
                  secureTextEntry
                  autoCapitalize="none"
                  autoComplete="new-password"
                  hint={fieldError ? undefined : PASSWORD_HINT}
                />

                <Field
                  label="Confirm new password"
                  placeholder="Type it again"
                  value={confirm}
                  onChangeText={(value) => {
                    setConfirm(value);
                    if (fieldError) setFieldError(null);
                  }}
                  secureTextEntry
                  autoCapitalize="none"
                  autoComplete="new-password"
                  onSubmitEditing={submit}
                />
              </View>

              {fieldError ? (
                <Txt className="mt-3 text-[12.5px]" style={{ color: C.alert }}>
                  {fieldError}
                </Txt>
              ) : null}

              <View className="mt-[18px]">
                <Button label="Set new password" onPress={submit} loading={busy} />
              </View>

              {error ? (
                <Unavailable
                  title={badToken ? 'That link has expired' : 'Could not reset your password'}
                  error={error}
                  className="mt-4"
                />
              ) : null}

              {badToken ? (
                <View className="mt-3">
                  <Button
                    label="Send me a new link"
                    variant="secondary"
                    onPress={() => router.replace(FORGOT_PASSWORD)}
                  />
                </View>
              ) : null}
            </>
          )}

          {done ? null : (
            <Pressable
              accessibilityRole="link"
              className="mt-6 items-center"
              onPress={() => router.replace(SIGN_IN)}>
              <TxtMed className="text-[12.5px] text-bone-secondary">Back to sign in</TxtMed>
            </Pressable>
          )}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
