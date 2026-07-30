import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as DocumentPicker from 'expo-document-picker';

import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Select } from '@/components/ui/select';
import { Eyebrow, FieldLabel, Mono, Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { Unavailable } from '@/components/unavailable';
import { api } from '@/api';
import type { CompanyRegistration } from '@/domain/types';
import { useSession } from '@/store/session';

/**
 * Countries with their registrar prefilled, so the founder does not have to
 * know what the body is called. Extend as the market expands.
 */
const REGISTRARS: Record<string, string> = {
  Nigeria: 'CAC',
  Ghana: 'RGD',
  Kenya: 'BRS',
  'South Africa': 'CIPC',
  'United Kingdom': 'Companies House',
  'United States': 'Secretary of State',
  Canada: 'Corporations Canada',
  India: 'MCA',
  Singapore: 'ACRA',
  Germany: 'Handelsregister',
  Netherlands: 'KvK',
  Other: '',
};

const COUNTRIES = Object.keys(REGISTRARS);

const MAX_DOC_BYTES = 10 * 1024 * 1024;

export default function VerifyCompany() {
  const insets = useSafeAreaInsets();
  const account = useSession((s) => s.founderAccount);
  const setFounderAccount = useSession((s) => s.setFounderAccount);

  const [country, setCountry] = useState(account?.registration?.country ?? '');
  const [legalName, setLegalName] = useState(account?.registration?.legalName ?? '');
  const [registrationNumber, setRegistrationNumber] = useState(account?.registration?.registrationNumber ?? '');
  const [registrar, setRegistrar] = useState(account?.registration?.registrar ?? '');
  const [document, setDocument] = useState(account?.registration?.document ?? '');
  const [docError, setDocError] = useState(false);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const inReview = account?.verification === 'in_review';
  const complete = country && legalName.trim() && registrationNumber.trim() && document;

  function pickCountry(value: string) {
    setCountry(value);
    // Prefill the registrar, but let the founder correct it.
    if (!registrar || REGISTRARS[registrar] !== undefined) setRegistrar(REGISTRARS[value] ?? '');
  }

  async function pickDocument() {
    const result = await DocumentPicker.getDocumentAsync({
      type: ['application/pdf', 'image/jpeg', 'image/png'],
      copyToCacheDirectory: true,
    });
    if (result.canceled) return;
    const file = result.assets[0];
    if ((file.size ?? 0) > MAX_DOC_BYTES) {
      setDocError(true);
      return;
    }
    setDocError(false);
    setDocument(file.name);
  }

  async function submit() {
    if (!complete) {
      setTouched(true);
      return;
    }
    setBusy(true);
    try {
      const registration: CompanyRegistration = {
        country,
        legalName: legalName.trim(),
        registrationNumber: registrationNumber.trim(),
        registrar: registrar.trim() || REGISTRARS[country] || 'Registrar',
        document,
      };
      setFounderAccount(await api.submitCompanyRegistration(registration));
      router.back();
    } catch (e) {
      // Stay on the screen: navigating back would imply it was submitted.
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView className="flex-1 bg-ground" behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View className="border-b border-line-soft px-[18px] pb-3" style={{ paddingTop: insets.top + 4 }}>
        <View className="h-[34px] flex-row items-center justify-between">
          <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={10}>
            <Txt className="text-[19px] text-ink">←</Txt>
          </Pressable>
          <Mono className="text-[10px] text-ink-faint" style={{ letterSpacing: 1.2 }}>
            COMPANY VERIFICATION
          </Mono>
          <View className="w-5" />
        </View>
      </View>

      <ScrollView
        className="flex-1"
        contentContainerStyle={{ padding: 18, paddingTop: 20 }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}>
        {inReview ? (
          <View
            className="mb-5 rounded-[12px] p-[14px]"
            style={{ borderWidth: 1, borderColor: 'rgba(0,112,243,0.35)', backgroundColor: 'rgba(0,112,243,0.08)' }}>
            <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: C.blue }}>
              IN REVIEW
            </Mono>
            <Txt className="mt-2 text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
              We are checking your registration against the registry. You will get a notification the moment it clears.
            </Txt>
          </View>
        ) : null}

        <Eyebrow>REGISTRATION</Eyebrow>
        <TxtSemi className="mb-1 mt-2 text-[23px]" style={{ letterSpacing: -0.7 }}>
          Prove your company is real
        </TxtSemi>
        <Txt className="mb-[22px] text-[13px] text-ink-dim" style={{ lineHeight: 20 }}>
          Investors only see companies that are registered in their own country. This is checked once.
        </Txt>

        <View className="gap-4">
          <Select
            label="Country of registration"
            placeholder="Select a country…"
            value={country}
            options={COUNTRIES}
            onChange={pickCountry}
          />
          <Field
            label="Registered legal name"
            placeholder="Northwind Labs Limited"
            value={legalName}
            onChangeText={setLegalName}
          />
          <Field
            label="Registration number"
            placeholder="RC 1234567"
            value={registrationNumber}
            onChangeText={setRegistrationNumber}
            autoCapitalize="characters"
            mono
          />
          <Field
            label="Registered with"
            placeholder="CAC"
            value={registrar}
            onChangeText={setRegistrar}
            hint="The government body you filed with. Prefilled from your country."
          />

          <View className="gap-[9px]">
            <FieldLabel>Certificate of incorporation</FieldLabel>
            {document ? (
              <View className="flex-row items-center gap-[11px] rounded-[11px] border border-line-strong bg-surface-1 p-[14px]">
                <View className="h-[34px] w-[34px] items-center justify-center rounded-[7px] border border-line-strong bg-surface-3">
                  <Mono className="text-[9px] text-ink-muted">
                    {document.split('.').pop()?.slice(0, 4).toUpperCase() ?? 'DOC'}
                  </Mono>
                </View>
                <View className="min-w-0 flex-1">
                  <Txt className="text-[13px]" numberOfLines={1}>
                    {document}
                  </Txt>
                  <Txt className="text-[11px] text-ink-faint">attached</Txt>
                </View>
                <Pressable accessibilityRole="button" onPress={pickDocument} hitSlop={8}>
                  <Txt className="text-[11.5px] text-ink-muted">Replace</Txt>
                </Pressable>
              </View>
            ) : (
              <Pressable
                accessibilityRole="button"
                onPress={pickDocument}
                className="w-full items-center gap-[6px] rounded-[11px] bg-surface-1 px-4 py-[26px]"
                style={{ borderWidth: 1.5, borderStyle: 'dashed', borderColor: C.lineDash }}>
                <Txt className="text-[19px] text-ink">↑</Txt>
                <TxtMed className="text-[13.5px] text-ink">Upload certificate</TxtMed>
                <Txt className="text-[11px] text-ink-faint">PDF, JPG or PNG · up to 10 MB</Txt>
              </Pressable>
            )}
            {docError ? (
              <ErrorNote text="File exceeds 10 MB. Compress the scan and try again." />
            ) : null}
          </View>

          {touched && !complete ? <ErrorNote text="Fill every field and attach your certificate to submit." /> : null}
        </View>

        <Txt className="mt-5 text-[11px] text-ink-faint" style={{ lineHeight: 17 }}>
          Your certificate is used only to confirm registration and is never shown to investors.
        </Txt>

        {error ? <Unavailable title="Verification is not live" error={error} className="mt-5" /> : null}
      </ScrollView>

      <View className="border-t border-line-soft bg-ground px-[18px] pt-3" style={{ paddingBottom: insets.bottom + 14 }}>
        <Button label={inReview ? 'Resubmit for review' : 'Submit for verification'} height={48} loading={busy} onPress={submit} />
      </View>
    </KeyboardAvoidingView>
  );
}

function ErrorNote({ text }: { text: string }) {
  return (
    <View
      className="rounded-[9px] px-[13px] py-[11px]"
      style={{ borderWidth: 1, borderColor: '#4a1d1d', backgroundColor: 'rgba(255,77,79,0.07)' }}>
      <Txt className="text-[12px]" style={{ color: '#ff8a8c', lineHeight: 18 }}>
        {text}
      </Txt>
    </View>
  );
}
