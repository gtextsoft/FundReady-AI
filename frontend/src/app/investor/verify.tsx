import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Select } from '@/components/ui/select';
import { Eyebrow, Mono, Txt, TxtSemi } from '@/components/ui/text';
import { Unavailable } from '@/components/unavailable';
import { api } from '@/api';
import { INVESTOR_TYPES, type InvestorCredentials, type InvestorType } from '@/domain/types';
import { useSession } from '@/store/session';

const COUNTRIES = [
  'Nigeria', 'Ghana', 'Kenya', 'South Africa', 'United Kingdom', 'United States',
  'Canada', 'India', 'Singapore', 'Germany', 'Netherlands', 'United Arab Emirates', 'Other',
];

/**
 * Investor verification — deliberately light.
 *
 * The point is accountability, not gatekeeping: a founder should be able to
 * see who is asking for their numbers. Four fields, no documents, no waiting.
 */
export default function VerifyInvestor() {
  const insets = useSafeAreaInsets();
  const account = useSession((s) => s.investorAccount);
  const setInvestorAccount = useSession((s) => s.setInvestorAccount);

  const [investorType, setInvestorType] = useState<string>(account?.credentials?.investorType ?? '');
  const [firm, setFirm] = useState(account?.credentials?.firm ?? '');
  const [country, setCountry] = useState(account?.credentials?.country ?? '');
  const [linkedinUrl, setLinkedinUrl] = useState(account?.credentials?.linkedinUrl ?? '');
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const complete = investorType && firm.trim() && country && linkedinUrl.trim();

  async function submit() {
    if (!complete) {
      setTouched(true);
      return;
    }
    setBusy(true);
    try {
      const credentials: InvestorCredentials = {
        investorType: investorType as InvestorType,
        firm: firm.trim(),
        country,
        linkedinUrl: linkedinUrl.trim(),
      };
      setInvestorAccount(await api.submitInvestorCredentials(credentials));
      router.back();
    } catch (e) {
      // Stay on the screen: navigating back would imply it was submitted.
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView className="flex-1 bg-obsidian" behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View className="border-b border-graphite-soft px-[18px] pb-3" style={{ paddingTop: insets.top + 4 }}>
        <View className="h-[34px] flex-row items-center justify-between">
          <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={10}>
            <Txt className="text-[19px] text-bone">←</Txt>
          </Pressable>
          <Mono className="text-[10px] text-bone-faint" style={{ letterSpacing: 1.2 }}>
            INVESTOR VERIFICATION
          </Mono>
          <View className="w-5" />
        </View>
      </View>

      <ScrollView
        className="flex-1"
        contentContainerStyle={{ padding: 18, paddingTop: 20 }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}>
        <Eyebrow>WHO YOU ARE</Eyebrow>
        <TxtSemi className="mb-1 mt-2 text-[23px]" style={{ letterSpacing: -0.7 }}>
          Verify your profile
        </TxtSemi>
        <Txt className="mb-[22px] text-[13px] text-bone-muted" style={{ lineHeight: 20 }}>
          Founders share real numbers with you, so they get to see who is asking. Four fields, no documents.
        </Txt>

        <View className="gap-4">
          <Select
            label="Investor type"
            placeholder="Select a type…"
            value={investorType}
            options={INVESTOR_TYPES}
            onChange={setInvestorType}
          />
          <Field label="Firm or fund" placeholder="Northwind Capital" value={firm} onChangeText={setFirm} />
          <Select
            label="Country"
            placeholder="Select a country…"
            value={country}
            options={COUNTRIES}
            onChange={setCountry}
          />
          <Field
            label="LinkedIn profile"
            placeholder="linkedin.com/in/yourname"
            value={linkedinUrl}
            onChangeText={setLinkedinUrl}
            autoCapitalize="none"
            keyboardType="url"
            hint="Used only to confirm you are who you say you are."
          />

          {touched && !complete ? (
            <View
              className="rounded-[9px] px-[13px] py-[11px]"
              style={{ borderWidth: 1, borderColor: '#4A1F1E', backgroundColor: 'rgba(242,85,78,0.07)' }}>
              <Txt className="text-[12px]" style={{ color: '#ff8a8c', lineHeight: 18 }}>
                Fill every field to verify.
              </Txt>
            </View>
          ) : null}

          {error ? <Unavailable title="Verification is not live" error={error} className="mt-4" /> : null}
        </View>
      </ScrollView>

      <View className="border-t border-graphite-soft bg-obsidian px-[18px] pt-3" style={{ paddingBottom: insets.bottom + 14 }}>
        <Button label="Verify profile" height={48} loading={busy} onPress={submit} />
      </View>
    </KeyboardAvoidingView>
  );
}
