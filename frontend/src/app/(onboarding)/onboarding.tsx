import { useEffect } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';
import * as DocumentPicker from 'expo-document-picker';

import { Button } from '@/components/ui/button';
import { Field, OptionGrid } from '@/components/ui/field';
import { Select } from '@/components/ui/select';
import { Segmented } from '@/components/ui/controls';
import { Eyebrow, FieldLabel, Mono, Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { companyNameFromEmail } from '@/domain/email';
import { ltvCacRatio } from '@/domain/scoring';
import { FOUNDER_STAGES, ONBOARDING_SECTORS, type RevModel } from '@/domain/types';
import { FOUNDER_HOME, route } from '@/lib/routes';
import { isStepValid, useFounder, type Step } from '@/store/founder';
import { useSession } from '@/store/session';

const MAX_DECK_BYTES = 25 * 1024 * 1024;

export default function Onboarding() {
  const insets = useSafeAreaInsets();

  const profile = useFounder((s) => s.profile);
  const step = useFounder((s) => s.step);
  const touched = useFounder((s) => s.touched);
  const deckError = useFounder((s) => s.deckError);
  const setField = useFounder((s) => s.setField);
  const setStep = useFounder((s) => s.setStep);
  const markTouched = useFounder((s) => s.markTouched);
  const uploadDeck = useFounder((s) => s.uploadDeck);
  const failUpload = useFounder((s) => s.failUpload);

  const email = useSession((s) => s.session?.email ?? '');

  // Seed the company name from the sign-up domain so the founder does not
  // retype what they already told us. Only ever fills a blank field, so it
  // cannot overwrite something they typed, and it stays fully editable.
  useEffect(() => {
    if (profile.company.trim()) return;
    const suggestion = companyNameFromEmail(email);
    if (suggestion) setField('company', suggestion);
    // Runs on the address changing, not on every keystroke in the field.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [email, setField]);

  const valid = isStepValid(profile, step);
  const showError = touched && !valid;

  function next() {
    if (!valid) {
      markTouched();
      return;
    }
    if (step < 4) setStep((step + 1) as Step);
    else router.push(route('/assessment'));
  }

  /** Step 1 backs out to the dashboard, not to sign-in — they are signed up. */
  function back() {
    if (step > 1) setStep((step - 1) as Step);
    else router.replace(FOUNDER_HOME);
  }

  async function pickDeck() {
    const result = await DocumentPicker.getDocumentAsync({
      type: [
        'application/pdf',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      ],
      copyToCacheDirectory: true,
    });
    if (result.canceled) return;
    const file = result.assets[0];
    if ((file.size ?? 0) > MAX_DECK_BYTES) {
      failUpload();
      return;
    }
    uploadDeck(file.name);
  }

  return (
    <KeyboardAvoidingView className="flex-1 bg-ground" behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {/* header */}
      <View className="border-b border-line-soft px-5 pb-[14px]" style={{ paddingTop: insets.top + 6 }}>
        <View className="h-[34px] flex-row items-center justify-between">
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Back"
            onPress={back}
            hitSlop={10}
            className="-ml-2 h-8 w-8 items-center justify-center">
            <Txt className="text-[19px] text-ink">←</Txt>
          </Pressable>
          <Mono className="text-[11px] text-ink-muted" style={{ letterSpacing: 0.6 }}>
            STEP {step} OF 4
          </Mono>
          <Pressable accessibilityRole="button" onPress={() => router.replace(FOUNDER_HOME)} hitSlop={10}>
            <Txt className="text-[12px] text-ink-dim">Save &amp; exit</Txt>
          </Pressable>
        </View>
        <View className="mt-[10px] flex-row gap-1">
          {[1, 2, 3, 4].map((i) => (
            <View
              key={i}
              className="h-[3px] flex-1 rounded-[3px]"
              style={{ backgroundColor: step >= i ? C.ink : '#242424' }}
            />
          ))}
        </View>
      </View>

      {/* body */}
      <ScrollView
        className="flex-1"
        contentContainerStyle={{ padding: 20, paddingTop: 24 }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}>
        <Animated.View key={step} entering={FadeInDown.duration(300)}>
          {step === 1 ? (
            <View>
              <Eyebrow>BASICS</Eyebrow>
              <TxtSemi className="mb-1 mt-2 text-[23px]" style={{ letterSpacing: -0.7 }}>
                Tell us who you are
              </TxtSemi>
              <Txt className="mb-[22px] text-[13px] text-ink-dim" style={{ lineHeight: 20 }}>
                Four fields. Roughly 30 seconds.
              </Txt>
              <View className="gap-4">
                <Field
                  label="Company name"
                  placeholder="Northwind Labs"
                  value={profile.company}
                  onChangeText={(v) => setField('company', v)}
                />
                <Select
                  label="Industry sector"
                  placeholder="Select a sector…"
                  value={profile.sector}
                  options={ONBOARDING_SECTORS}
                  onChange={(v) => setField('sector', v)}
                />
                <Field
                  label="Headquarters"
                  placeholder="Lagos, Nigeria"
                  value={profile.location}
                  onChangeText={(v) => setField('location', v)}
                />
                <Field
                  label="Founding year"
                  placeholder="2023"
                  value={profile.year}
                  onChangeText={(v) => setField('year', v)}
                  keyboardType="number-pad"
                  mono
                />
              </View>
            </View>
          ) : null}

          {step === 2 ? (
            <View>
              <Eyebrow>TRACTION &amp; REVENUE</Eyebrow>
              <TxtSemi className="mb-1 mt-2 text-[23px]" style={{ letterSpacing: -0.7 }}>
                How are you growing?
              </TxtSemi>
              <Txt className="mb-[22px] text-[13px] text-ink-dim" style={{ lineHeight: 20 }}>
                Approximate is fine — you can revise before investors see it.
              </Txt>
              <View className="gap-5">
                <View className="gap-[9px]">
                  <FieldLabel>Current stage</FieldLabel>
                  <OptionGrid options={FOUNDER_STAGES} value={profile.stage} onChange={(v) => setField('stage', v)} />
                </View>

                <View className="gap-[9px]">
                  <View className="flex-row items-center justify-between">
                    <FieldLabel>Recurring revenue</FieldLabel>
                    <Segmented
                      options={[
                        { value: 'MRR' as RevModel, label: 'MRR' },
                        { value: 'ARR' as RevModel, label: 'ARR' },
                      ]}
                      value={profile.revModel}
                      onChange={(v) => setField('revModel', v)}
                    />
                  </View>
                  <Field
                    prefix="$"
                    suffix={profile.revModel}
                    placeholder="48000"
                    value={profile.revenue}
                    onChangeText={(v) => setField('revenue', v)}
                    keyboardType="number-pad"
                    mono
                  />
                </View>

                <Field
                  label="Month-over-month growth"
                  suffix="% MoM"
                  placeholder="14"
                  value={profile.growth}
                  onChangeText={(v) => setField('growth', v)}
                  keyboardType="decimal-pad"
                  mono
                  hint="Seed benchmark: 8–15% · Top decile: 20%+"
                />
              </View>
            </View>
          ) : null}

          {step === 3 ? (
            <View>
              <Eyebrow>MARKET &amp; UNIT ECONOMICS</Eyebrow>
              <TxtSemi className="mb-1 mt-2 text-[23px]" style={{ letterSpacing: -0.7 }}>
                Does the maths work?
              </TxtSemi>
              <Txt className="mb-[22px] text-[13px] text-ink-dim" style={{ lineHeight: 20 }}>
                This section moves your score more than any other.
              </Txt>
              <View className="gap-4">
                <Field
                  label="Total addressable market"
                  prefix="$"
                  suffix="Billion"
                  placeholder="12"
                  value={profile.tam}
                  onChangeText={(v) => setField('tam', v)}
                  keyboardType="decimal-pad"
                  mono
                />
                <Field
                  label="Gross margin"
                  suffix="%"
                  placeholder="78"
                  value={profile.margin}
                  onChangeText={(v) => setField('margin', v)}
                  keyboardType="decimal-pad"
                  mono
                />
                <View className="flex-row gap-[10px]">
                  <View className="flex-1">
                    <Field
                      label="CAC"
                      prefix="$"
                      placeholder="320"
                      value={profile.cac}
                      onChangeText={(v) => setField('cac', v)}
                      keyboardType="number-pad"
                      mono
                    />
                  </View>
                  <View className="flex-1">
                    <Field
                      label="LTV"
                      prefix="$"
                      placeholder="1450"
                      value={profile.ltv}
                      onChangeText={(v) => setField('ltv', v)}
                      keyboardType="number-pad"
                      mono
                    />
                  </View>
                </View>
                <RatioRow />
              </View>
            </View>
          ) : null}

          {step === 4 ? (
            <View>
              <Eyebrow>TEAM &amp; DECK</Eyebrow>
              <TxtSemi className="mb-1 mt-2 text-[23px]" style={{ letterSpacing: -0.7 }}>
                Who is building it?
              </TxtSemi>
              <Txt className="mb-[22px] text-[13px] text-ink-dim" style={{ lineHeight: 20 }}>
                Last step. Then the model runs.
              </Txt>
              <View className="gap-5">
                <Field
                  label="Full-time founders"
                  placeholder="2"
                  value={profile.founders}
                  onChangeText={(v) => setField('founders', v)}
                  keyboardType="number-pad"
                  mono
                />

                <View className="gap-[9px]">
                  <FieldLabel>Technical co-founder in-house?</FieldLabel>
                  <OptionGrid
                    options={['Yes', 'No'] as const}
                    value={profile.technical}
                    onChange={(v) => setField('technical', v)}
                  />
                </View>

                <View className="gap-[9px]">
                  <FieldLabel>Pitch deck / financial model</FieldLabel>

                  {profile.deck ? (
                    <View className="flex-row items-center gap-[11px] rounded-[11px] border border-line-strong bg-surface-1 p-[14px]">
                      <View className="h-[34px] w-[34px] items-center justify-center rounded-[7px] border border-line-strong bg-surface-3">
                        <Mono className="text-[9px] text-ink-muted">
                          {profile.deck.split('.').pop()?.slice(0, 4).toUpperCase() ?? 'DOC'}
                        </Mono>
                      </View>
                      <View className="min-w-0 flex-1">
                        <Txt className="text-[13px]" numberOfLines={1}>
                          {profile.deck}
                        </Txt>
                        <Txt className="text-[11px] text-ink-faint">uploaded</Txt>
                      </View>
                      <View className="h-[18px] w-[18px] items-center justify-center rounded-full" style={{ backgroundColor: C.grn }}>
                        <Txt className="text-[11px] text-ground">✓</Txt>
                      </View>
                    </View>
                  ) : (
                    <Pressable
                      accessibilityRole="button"
                      onPress={pickDeck}
                      className="w-full items-center gap-[6px] rounded-[11px] bg-surface-1 px-4 py-[26px]"
                      style={{ borderWidth: 1.5, borderStyle: 'dashed', borderColor: C.lineDash }}>
                      <Txt className="text-[19px] text-ink">↑</Txt>
                      <TxtMed className="text-[13.5px] text-ink">Drop a file or browse</TxtMed>
                      <Txt className="text-[11px] text-ink-faint">PDF, PPTX or XLSX · up to 25 MB</Txt>
                    </Pressable>
                  )}

                  {deckError ? (
                    <View
                      className="rounded-[9px] px-[13px] py-[11px]"
                      style={{ borderWidth: 1, borderColor: '#4a1d1d', backgroundColor: 'rgba(255,77,79,0.07)' }}>
                      <Txt className="text-[12px]" style={{ color: '#ff8a8c', lineHeight: 18 }}>
                        File exceeds 25 MB. Compress the deck or link a Drive URL instead.
                      </Txt>
                    </View>
                  ) : null}
                </View>
              </View>
            </View>
          ) : null}

          {showError ? (
            <View
              className="mt-[18px] rounded-[9px] px-[13px] py-[11px]"
              style={{ borderWidth: 1, borderColor: '#4a1d1d', backgroundColor: 'rgba(255,77,79,0.07)' }}>
              <Txt className="text-[12px]" style={{ color: '#ff8a8c', lineHeight: 18 }}>
                Complete every field on this step to continue.
              </Txt>
            </View>
          ) : null}
        </Animated.View>
      </ScrollView>

      {/* footer */}
      <View className="border-t border-line-soft bg-ground px-5 pt-[14px]" style={{ paddingBottom: insets.bottom + 16 }}>
        <Button label={step === 4 ? 'Run AI assessment' : 'Continue'} height={50} onPress={next} />
      </View>
    </KeyboardAvoidingView>
  );
}

/** Live LTV:CAC readout — turns green once the ratio clears 3:1. */
function RatioRow() {
  const profile = useFounder((s) => s.profile);
  const ratio = ltvCacRatio(profile);
  const label = ratio > 0 ? `${ratio.toFixed(1)} : 1` : '—';
  const color = ratio >= 3 ? C.grn : ratio > 0 ? C.amb : C.inkFaint;

  return (
    <View className="flex-row items-center justify-between rounded-[9px] border border-line bg-surface-1 px-[14px] py-[13px]">
      <Txt className="text-[12px] text-ink-muted">LTV : CAC ratio</Txt>
      <Mono className="text-[14px]" style={{ color }}>
        {label}
      </Mono>
    </View>
  );
}
