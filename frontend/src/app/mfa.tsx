import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { Redirect, router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Mark } from '@/components/ui/mark';
import { Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { homeFor, SIGN_IN } from '@/lib/routes';
import { useSession } from '@/store/session';

/** Six digits from an authenticator, or a longer single-use recovery code. */
const TOTP_LENGTH = 6;

/**
 * The second factor.
 *
 * Reached only when login answered `mfa_required`. The challenge token from
 * that response lives in the session store, grants nothing on its own, and
 * expires in five minutes -- so arriving here without one means the attempt
 * is stale and the only honest thing to do is send the user back to sign in.
 */
export default function Mfa() {
  const insets = useSafeAreaInsets();

  const mfaToken = useSession((s) => s.mfaToken);
  const verifyMfa = useSession((s) => s.verifyMfa);
  const clearMfa = useSession((s) => s.clearMfa);
  const busy = useSession((s) => s.busy);
  const error = useSession((s) => s.error);

  const [code, setCode] = useState('');

  if (!mfaToken) return <Redirect href={SIGN_IN} />;

  const usable = code.trim().length >= TOTP_LENGTH;

  async function submit() {
    if (!usable) return;
    const session = await verifyMfa(code);
    if (session) router.replace(homeFor(session.role));
  }

  function cancel() {
    clearMfa();
    router.replace(SIGN_IN);
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
            Enter your code.
          </TxtSemi>
          <Txt className="mb-7 text-[13px] text-ink-muted" style={{ lineHeight: 20 }}>
            Open your authenticator app and enter the current six-digit code. You can use one of your
            recovery codes instead — each of those works once.
          </Txt>

          <Field
            label="Authentication code"
            placeholder="123456"
            value={code}
            onChangeText={setCode}
            autoCapitalize="characters"
            autoComplete="one-time-code"
            keyboardType="default"
            onSubmitEditing={submit}
          />

          <View className="mt-[18px]">
            <Button label="Verify" loading={busy} disabled={!usable} onPress={submit} />
          </View>

          {error ? (
            <View
              className="mt-4 rounded-[11px] p-[13px]"
              style={{ borderWidth: 1, borderColor: '#4a1d1d', backgroundColor: 'rgba(255,77,79,0.08)' }}>
              <Txt className="text-[12.5px]" style={{ color: C.red, lineHeight: 19 }}>
                {error}
              </Txt>
            </View>
          ) : null}

          <Pressable accessibilityRole="link" className="mt-6 items-center" onPress={cancel}>
            <TxtMed className="text-[12.5px] text-ink-muted">Back to sign in</TxtMed>
          </Pressable>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
