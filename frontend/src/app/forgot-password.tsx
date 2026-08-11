import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Mark } from '@/components/ui/mark';
import { Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { Unavailable } from '@/components/unavailable';
import { api } from '@/api';
import { SIGN_IN } from '@/lib/routes';

export default function ForgotPassword() {
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.requestPasswordReset(email.trim());
      setSent(true);
    } catch (e) {
      // Never claim a link was sent when nothing was sent.
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView className="flex-1 bg-obsidian" behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
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

          <TxtSemi className="mb-7 mt-7 text-[30px]" style={{ letterSpacing: -1.1, lineHeight: 33 }}>
            Reset your password.
          </TxtSemi>

          {sent ? (
            <View className="rounded-[11px] border border-graphite bg-carbon-low p-4">
              <View className="mb-2 flex-row items-center gap-2">
                <View className="h-[6px] w-[6px] rounded-full" style={{ backgroundColor: C.signal }} />
                <TxtSemi className="text-[13.5px]">Check your inbox</TxtSemi>
              </View>
              {/* Deliberately does not confirm whether the address has an
                  account — that would leak which emails are registered. */}
              <Txt className="text-[12.5px] text-bone-secondary" style={{ lineHeight: 19 }}>
                If {email.trim() || 'that address'} has an account, a reset link is on its way. The
                link can be used once and expires in an hour.
              </Txt>
            </View>
          ) : (
            <>
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
                <Button label="Send reset link" onPress={submit} loading={busy} />
              </View>
              {error ? <Unavailable title="Password reset is not live" error={error} className="mt-4" /> : null}
            </>
          )}

          <Pressable accessibilityRole="link" className="mt-6 items-center" onPress={() => router.replace(SIGN_IN)}>
            <TxtMed className="text-[12.5px] text-bone-secondary">Back to sign in</TxtMed>
          </Pressable>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
