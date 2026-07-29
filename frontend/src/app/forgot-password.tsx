import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Mark } from '@/components/ui/mark';
import { Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { api } from '@/api';
import { SIGN_IN } from '@/lib/routes';

export default function ForgotPassword() {
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      await api.requestPasswordReset(email.trim());
      setSent(true);
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

          <TxtSemi className="mb-7 mt-7 text-[30px]" style={{ letterSpacing: -1.1, lineHeight: 33 }}>
            Reset your password.
          </TxtSemi>

          {sent ? (
            <View className="rounded-[11px] border border-line bg-surface-1 p-4">
              <View className="mb-2 flex-row items-center gap-2">
                <View className="h-[6px] w-[6px] rounded-full" style={{ backgroundColor: C.grn }} />
                <TxtSemi className="text-[13.5px]">Check your inbox</TxtSemi>
              </View>
              {/* Deliberately does not confirm whether the address has an
                  account — that would leak which emails are registered. */}
              <Txt className="text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
                If {email.trim() || 'that address'} has an account, a reset link is on its way. The link expires in 30
                minutes.
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
            </>
          )}

          <Pressable accessibilityRole="link" className="mt-6 items-center" onPress={() => router.replace(SIGN_IN)}>
            <TxtMed className="text-[12.5px] text-ink-muted">Back to sign in</TxtMed>
          </Pressable>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
