import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { Redirect, router, type Href } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Mark } from '@/components/ui/mark';
import { Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { homeFor } from '@/lib/routes';
import { useSession } from '@/store/session';

/**
 * Log in. The role is a property of the account, so unlike sign-up there is
 * nothing to choose here — the session decides which side of the marketplace
 * opens.
 */
export default function SignIn() {
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const status = useSession((s) => s.status);
  const role = useSession((s) => s.role);
  const signIn = useSession((s) => s.signIn);
  const busy = useSession((s) => s.busy);
  const error = useSession((s) => s.error);

  if (status === 'signedIn') return <Redirect href={homeFor(role)} />;

  async function submit() {
    const session = await signIn(email.trim(), password);
    if (session) router.replace(homeFor(session.role));
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

          <TxtSemi className="mb-8 mt-7 text-[30px]" style={{ letterSpacing: -1.1, lineHeight: 33 }}>
            Welcome back.
          </TxtSemi>

          <View className="gap-[10px]">
            <Field
              label="Work email"
              placeholder="you@company.com"
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
            />
            <Field
              label="Password"
              placeholder="••••••••••"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoComplete="current-password"
              onSubmitEditing={submit}
            />
          </View>

          <Pressable
            accessibilityRole="link"
            className="mt-3 self-end"
            hitSlop={8}
            onPress={() => router.push('/forgot-password' as Href)}>
            <Txt className="text-[12px] text-ink-muted">Forgot password?</Txt>
          </Pressable>

          {error ? (
            <View
              className="mt-4 rounded-[9px] px-[13px] py-[11px]"
              style={{ borderWidth: 1, borderColor: '#4a1d1d', backgroundColor: 'rgba(255,77,79,0.07)' }}>
              <Txt className="text-[12px]" style={{ color: '#ff8a8c', lineHeight: 18 }}>
                {error}
              </Txt>
            </View>
          ) : null}

          <View className="mt-[18px]">
            <Button label="Sign in" onPress={submit} loading={busy} />
          </View>

          <Pressable
            accessibilityRole="link"
            className="mt-6 items-center"
            onPress={() => router.replace('/sign-up' as Href)}>
            <TxtMed className="text-[12.5px] text-ink-muted">New to SACI FundMe? Create an account</TxtMed>
          </Pressable>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
