import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { Redirect, router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Segmented } from '@/components/ui/controls';
import { Field } from '@/components/ui/field';
import { Mark } from '@/components/ui/mark';
import { Mono, Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { api, type DomainSso, type Role } from '@/api';
import { checkFounderEmail, emailDomain, isValidEmail } from '@/domain/email';
import { homeFor, ONBOARDING, SIGN_IN } from '@/lib/routes';
import { useSession } from '@/store/session';

const ROLES = [
  { value: 'founder' as Role, label: "I'm raising" },
  { value: 'investor' as Role, label: "I'm investing" },
];

/** Mirrors the server's minimum (identity/schemas.py). Kept in step by hand. */
const MIN_PASSWORD = 12;

/** The headline is the only copy above the form — the subhead was removed. */
const HEADLINE: Record<Role, string> = {
  founder: 'Get funded on evidence, not vibes.',
  investor: 'Back companies on evidence, not vibes.',
};

export default function SignUp() {
  const insets = useSafeAreaInsets();
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [role, setRole] = useState<Role>('founder');
  const [nameError, setNameError] = useState<string | null>(null);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [sso, setSso] = useState<DomainSso | null>(null);

  const status = useSession((s) => s.status);
  const sessionRole = useSession((s) => s.role);
  const signUp = useSession((s) => s.signUp);
  const signInWithSso = useSession((s) => s.signInWithSso);
  const busy = useSession((s) => s.busy);
  const error = useSession((s) => s.error);
  const clearError = useSession((s) => s.clearError);

  if (status === 'signedIn') return <Redirect href={homeFor(sessionRole)} />;

  /** Founders go straight into the assessment; investors into dealflow. */
  const landing = role === 'investor' ? homeFor('investor') : ONBOARDING;

  function onChangeEmail(value: string) {
    setEmail(value);
    if (emailError) setEmailError(null);
    if (sso) setSso(null);
    if (error) clearError();
  }

  function switchRole(next: Role) {
    setRole(next);
    setEmailError(null);
    setSso(null);
    clearError();
  }

  /**
   * On blur, reject a personal domain immediately and ask the backend whether
   * the company runs single sign-on. Investors skip both — angels legitimately
   * operate from personal addresses.
   */
  async function onBlurEmail() {
    if (role !== 'founder' || !email.trim()) return;

    const verdict = checkFounderEmail(email);
    if (!verdict.ok) {
      setEmailError(verdict.message);
      setSso(null);
      return;
    }

    setEmailError(null);
    try {
      const lookup = await api.lookupEmailDomain(verdict.domain);
      setSso(lookup.sso);
    } catch {
      setSso(null); // A failed lookup just means the password form stays.
    }
  }

  async function submit() {
    if (!firstName.trim() || !lastName.trim()) {
      setNameError('Enter both your first and last name.');
      return;
    }

    if (!email.trim()) {
      setEmailError('Enter your email address.');
      return;
    }

    if (role === 'founder') {
      const verdict = checkFounderEmail(email);
      if (!verdict.ok) {
        setEmailError(verdict.message);
        return;
      }
    } else if (!isValidEmail(email)) {
      setEmailError('That does not look like an email address.');
      return;
    }

    // The server rejects anything shorter, so say so here rather than
    // round-tripping to find out.
    if (password.length < MIN_PASSWORD) {
      setPasswordError(`Use at least ${MIN_PASSWORD} characters.`);
      return;
    }

    // Catches the typo before it becomes an account nobody can log into.
    if (confirm !== password) {
      setPasswordError('Both passwords must match.');
      return;
    }

    const session = await signUp({
      email: email.trim(),
      password,
      role,
      firstName: firstName.trim(),
      lastName: lastName.trim(),
    });
    if (session) router.replace(landing);
  }

  async function continueWithSso() {
    const session = await signInWithSso(emailDomain(email), role);
    if (session) router.replace(landing);
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
            {HEADLINE[role]}
          </TxtSemi>

          <Segmented options={ROLES} value={role} onChange={switchRole} grow size="md" />

          <View className="mt-5 gap-[10px]">
            <View className="flex-row gap-[10px]">
              <View className="flex-1">
                <Field
                  label="First name"
                  placeholder="Ada"
                  value={firstName}
                  onChangeText={(v) => {
                    setFirstName(v);
                    if (nameError) setNameError(null);
                  }}
                  autoCapitalize="words"
                  autoComplete="given-name"
                />
              </View>
              <View className="flex-1">
                <Field
                  label="Last name"
                  placeholder="Nwosu"
                  value={lastName}
                  onChangeText={(v) => {
                    setLastName(v);
                    if (nameError) setNameError(null);
                  }}
                  autoCapitalize="words"
                  autoComplete="family-name"
                />
              </View>
            </View>
            <Field
              label={role === 'founder' ? 'Company email' : 'Email'}
              placeholder={role === 'investor' ? 'you@fund.com' : 'you@yourcompany.com'}
              value={email}
              onChangeText={onChangeEmail}
              onBlur={onBlurEmail}
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
              hint={
                role === 'founder' && !emailError
                  ? 'Must be your own company domain — not Gmail, Yahoo or similar.'
                  : undefined
              }
            />
            {!sso ? (
              <>
                <Field
                  label="Password"
                  placeholder="••••••••••"
                  value={password}
                  onChangeText={(value) => {
                    setPassword(value);
                    if (passwordError) setPasswordError(null);
                  }}
                  secureTextEntry
                  autoComplete="new-password"
                  hint={passwordError ? undefined : `At least ${MIN_PASSWORD} characters.`}
                />
                <Field
                  label="Confirm password"
                  placeholder="••••••••••"
                  value={confirm}
                  onChangeText={(value) => {
                    setConfirm(value);
                    if (passwordError) setPasswordError(null);
                  }}
                  secureTextEntry
                  autoComplete="new-password"
                  onSubmitEditing={submit}
                />
              </>
            ) : null}
          </View>

          {nameError ? <ErrorNote text={nameError} /> : null}
          {emailError && !nameError ? <ErrorNote text={emailError} /> : null}
          {passwordError && !nameError && !emailError ? <ErrorNote text={passwordError} /> : null}
          {error && !nameError && !emailError && !passwordError ? <ErrorNote text={error} /> : null}

          {sso ? (
            /* The company runs its own identity provider, so we hand off to it
               rather than minting another password. */
            <View className="mt-4 gap-3">
              <View
                className="rounded-[11px] p-[13px]"
                style={{ borderWidth: 1, borderColor: 'rgba(0,112,243,0.35)', backgroundColor: 'rgba(0,112,243,0.08)' }}>
                <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: C.blue }}>
                  SINGLE SIGN-ON
                </Mono>
                <Txt className="mt-2 text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
                  {emailDomain(email)} uses {sso.displayName}. Sign in with your work account — no new password.
                </Txt>
              </View>
              <Button label={`Continue with ${sso.displayName}`} onPress={continueWithSso} loading={busy} />
            </View>
          ) : (
            <View className="mt-[18px]">
              <Button
                label={role === 'investor' ? 'Create investor account' : 'Create founder account'}
                onPress={submit}
                loading={busy}
              />
            </View>
          )}

          <Pressable accessibilityRole="link" className="mt-6 items-center" onPress={() => router.replace(SIGN_IN)}>
            <TxtMed className="text-[12.5px] text-ink-muted">Already have an account? Sign in</TxtMed>
          </Pressable>
        </View>

        <Txt className="text-center text-[11px] text-ink-faint" style={{ lineHeight: 17 }}>
          By continuing you agree that SACI may share your anonymised metrics with vetted investors. You control every
          direct introduction.
        </Txt>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function ErrorNote({ text }: { text: string }) {
  return (
    <View
      className="mt-4 rounded-[9px] px-[13px] py-[11px]"
      style={{ borderWidth: 1, borderColor: '#4a1d1d', backgroundColor: 'rgba(255,77,79,0.07)' }}>
      <Txt className="text-[12px]" style={{ color: '#ff8a8c', lineHeight: 18 }}>
        {text}
      </Txt>
    </View>
  );
}
