import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Mark } from '@/components/ui/mark';
import { Mono, Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { Unavailable } from '@/components/unavailable';
import { C } from '@/theme/tokens';
import { api, ApiFailure, RESEND_COOLDOWN_MS } from '@/api';
import { isValidEmail } from '@/domain/email';
import { checkPassword, PASSWORD_HINT } from '@/domain/password';
import { FORGOT_PASSWORD, SIGN_IN } from '@/lib/routes';

/**
 * Complete a password reset with the emailed six-digit code.
 *
 * Reached from forgot-password (email prefilled) or typed manually. There is
 * deliberately no deep-link token: the email carries a code, checked against
 * one named account — same shape as email verification.
 *
 * **Usable while signed out.** The endpoint takes no authorization, and someone
 * resetting a password is very often locked out of the account.
 */
export default function ResetPassword() {
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ email?: string | string[] }>();
  const paramEmail = Array.isArray(params.email) ? params.email[0] : params.email;

  const [email, setEmail] = useState(paramEmail?.trim() ?? '');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [busy, setBusy] = useState<'reset' | 'resend' | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState(false);
  const [sentAt, setSentAt] = useState<number | null>(paramEmail ? Date.now() : null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (paramEmail?.trim()) setEmail(paramEmail.trim());
  }, [paramEmail]);

  const cooldownLeft = sentAt === null ? 0 : Math.max(0, sentAt + RESEND_COOLDOWN_MS - now);
  const cooldownSeconds = Math.ceil(cooldownLeft / 1000);

  useEffect(() => {
    if (cooldownLeft <= 0) return;
    const id = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(id);
  }, [cooldownLeft]);

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
    if (!isValidEmail(email)) {
      setFieldError('Enter the email the code was sent to.');
      return;
    }
    const digits = code.replace(/[\s-]/g, '');
    if (digits.length !== 6) {
      setFieldError('Enter the six-digit code from your email.');
      return;
    }

    setBusy('reset');
    setFieldError(null);
    setError(null);
    try {
      await api.resetPassword(email.trim(), code, password);
      setDone(true);
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
      await api.requestPasswordReset(email.trim());
      setSentAt(Date.now());
      setNow(Date.now());
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  // Unknown, expired and already-used codes are one indistinguishable
  // failure by design, so the offer is always the same: get a fresh code.
  const badCode = error instanceof ApiFailure && error.code === 'validation';

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

          <TxtSemi
            className="mb-3 mt-7 text-[30px]"
            style={{ letterSpacing: -1.1, lineHeight: 33 }}>
            {done ? 'Password changed.' : 'Choose a new password.'}
          </TxtSemi>

          {done ? (
            <>
              <View className="mb-6 rounded-[11px] border border-line bg-surface-1 p-4">
                <View className="mb-2 flex-row items-center gap-2">
                  <View
                    className="h-[6px] w-[6px] rounded-full"
                    style={{ backgroundColor: C.grn }}
                  />
                  <Mono className="text-[10px]" style={{ letterSpacing: 1, color: C.grn }}>
                    SIGNED OUT EVERYWHERE
                  </Mono>
                </View>
                <Txt className="text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
                  Every device signed in to this account has been signed out, including any
                  that were not yours. Sign in again with your new password.
                </Txt>
              </View>
              <Button label="Sign in" onPress={() => router.replace(SIGN_IN)} />
            </>
          ) : (
            <>
              <Txt className="mb-6 text-[13px] text-ink-muted" style={{ lineHeight: 20 }}>
                Enter the six-digit code from your email, then pick a new password. Every other
                device will be signed out.
              </Txt>

              <View className="gap-[14px]">
                <Field
                  label="Work email"
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

                <Field
                  label="Reset code"
                  placeholder="Six digits from your email"
                  value={code}
                  onChangeText={(value) => {
                    setCode(value);
                    if (error) setError(null);
                    if (fieldError) setFieldError(null);
                  }}
                  autoCapitalize="none"
                  keyboardType="number-pad"
                  mono
                />

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
                <Txt className="mt-3 text-[12.5px]" style={{ color: C.red }}>
                  {fieldError}
                </Txt>
              ) : null}

              <View className="mt-[18px] gap-3">
                <Button
                  label="Set new password"
                  onPress={submit}
                  loading={busy === 'reset'}
                  disabled={busy !== null}
                />
                <Button
                  label={
                    cooldownLeft > 0
                      ? `Resend code in ${cooldownSeconds}s`
                      : busy === 'resend'
                        ? 'Sending…'
                        : 'Resend code'
                  }
                  variant="secondary"
                  onPress={resend}
                  loading={busy === 'resend'}
                  disabled={busy !== null || cooldownLeft > 0 || !isValidEmail(email)}
                />
              </View>

              {error ? (
                <Unavailable
                  title={badCode ? 'That code is invalid or has expired' : 'Could not reset your password'}
                  error={error}
                  className="mt-4"
                />
              ) : null}

              {badCode ? (
                <View className="mt-3">
                  <Button
                    label="Start over"
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
              <TxtMed className="text-[12.5px] text-ink-muted">Back to sign in</TxtMed>
            </Pressable>
          )}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
