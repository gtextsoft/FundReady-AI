import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Mark } from '@/components/ui/mark';
import { Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { Unavailable } from '@/components/unavailable';
import { api } from '@/api';
import { RESET_PASSWORD, SIGN_IN, route } from '@/lib/routes';

/**
 * Start a password reset by emailing a six-digit code.
 *
 * Always shows the same success copy whether or not the address has an
 * account — confirming registration would be an enumeration leak. After a
 * successful send the user continues to the code + new-password screen.
 */
export default function ForgotPassword() {
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit() {
    const trimmed = email.trim();
    setBusy(true);
    setError(null);
    try {
      await api.requestPasswordReset(trimmed);
      router.replace(route(`${RESET_PASSWORD}?email=${encodeURIComponent(trimmed)}`));
    } catch (e) {
      // Never claim a code was sent when nothing was sent.
      setError(e);
    } finally {
      setBusy(false);
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
            Reset your password.
          </TxtSemi>
          <Txt className="mb-7 text-[13px] text-ink-muted" style={{ lineHeight: 20 }}>
            We will email a six-digit code. Enter it on the next screen with your new password.
          </Txt>

          <Field
            label="Work email"
            placeholder="you@company.com"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            autoComplete="email"
            keyboardType="email-address"
            onSubmitEditing={submit}
          />
          <View className="mt-[18px]">
            <Button label="Send reset code" onPress={submit} loading={busy} />
          </View>
          {error ? <Unavailable title="Password reset is not live" error={error} className="mt-4" /> : null}

          <Pressable accessibilityRole="link" className="mt-6 items-center" onPress={() => router.replace(SIGN_IN)}>
            <TxtMed className="text-[12.5px] text-ink-muted">Back to sign in</TxtMed>
          </Pressable>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
