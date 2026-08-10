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
import { COST_TRENDS, FOUNDER_STAGES, ONBOARDING_SECTORS, type RevModel } from '@/domain/types';
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

  const loaded = useFounder((s) => s.loaded);
  const load = useFounder((s) => s.load);

  const email = useSession((s) => s.session?.email ?? '');

  // Resume where they stopped. Onboarding is five screens of typing and it is
  // routinely abandoned halfway; without this, reopening the app starts from
  // an empty form even though the answers are on the server.
  useEffect(() => {
    if (!loaded) void load().catch(() => undefined);
  }, [loaded, load]);

  // Seed the company name from the sign-up domain so the founder does not
  // retype what they already told us. Only ever fills a blank field, so it
  // cannot overwrite something they typed or something already saved, and it
  // stays fully editable. Waits for the load so it cannot win a race against
  // the stored name.
  useEffect(() => {
    if (!loaded || profile.company.trim()) return;
    const suggestion = companyNameFromEmail(email);
    if (suggestion) setField('company', suggestion);
    // Runs on the address changing, not on every keystroke in the field.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [email, setField, loaded]);

  const valid = isStepValid(profile, step);
  const showError = touched && !valid;

  function next() {
    if (!valid) {
      markTouched();
      return;
    }
    if (step < 5) setStep((step + 1) as Step);
    // `replace`, not `push`: once the assessment is submitted the form must
    // not still be sitting underneath it. Going back into a half-edited copy
    // of answers that have already been sent is how someone ends up
    // resubmitting a different profile than the one they were scored on.
    else router.replace(route('/assessment'));
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
            STEP {step} OF 5
          </Mono>
          <Pressable accessibilityRole="button" onPress={() => router.replace(FOUNDER_HOME)} hitSlop={10}>
            <Txt className="text-[12px] text-ink-dim">Save &amp; exit</Txt>
          </Pressable>
        </View>
        <View className="mt-[10px] flex-row gap-1">
          {[1, 2, 3, 4, 5].map((i) => (
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
                />
                <Field
                  label="What does the business do?"
                  placeholder="One or two sentences, as you would say it out loud."
                  value={profile.description}
                  onChangeText={(v) => setField('description', v)}
                  multiline
                />
                <Field
                  label="How does it make money?"
                  placeholder="Subscription, commission, one-off sales…"
                  value={profile.businessModel}
                  onChangeText={(v) => setField('businessModel', v)}
                  multiline
                />
                <Field
                  label="Website"
                  placeholder="northwindlabs.com"
                  value={profile.website}
                  onChangeText={(v) => setField('website', v)}
                  autoCapitalize="none"
                  keyboardType="url"
                  hint="Optional. It gives the audit somewhere to corroborate what you have said."
                />
              </View>
            </View>
          ) : null}

          {step === 2 ? (
            <View>
              <Eyebrow>MONEY</Eyebrow>
              <TxtSemi className="mb-1 mt-2 text-[23px]" style={{ letterSpacing: -0.7 }}>
                What comes in, what goes out
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
                  label="Monthly costs"
                  prefix="$"
                  placeholder="62000"
                  value={profile.costs}
                  onChangeText={(v) => setField('costs', v)}
                  keyboardType="number-pad"
                  mono
                  hint="Everything you spend in a normal month, including salaries."
                />

                <Field
                  label="Cost of delivering that revenue"
                  prefix="$"
                  placeholder="9000"
                  value={profile.costOfRevenue}
                  onChangeText={(v) => setField('costOfRevenue', v)}
                  keyboardType="number-pad"
                  mono
                  hint="Hosting, support, payment fees — what it costs to serve customers. We work out your margin from this."
                />

                <Field
                  label="Cash in the bank"
                  prefix="$"
                  placeholder="410000"
                  value={profile.cash}
                  onChangeText={(v) => setField('cash', v)}
                  keyboardType="number-pad"
                  mono
                  hint="With your costs above, this is what sets your runway."
                />

                <View className="flex-row gap-[10px]">
                  <View className="flex-1">
                    <Field
                      label="Raised so far"
                      prefix="$"
                      placeholder="150000"
                      value={profile.totalRaised}
                      onChangeText={(v) => setField('totalRaised', v)}
                      keyboardType="number-pad"
                      mono
                    />
                  </View>
                  <View className="flex-1">
                    <Field
                      label="Looking to raise"
                      prefix="$"
                      placeholder="500000"
                      value={profile.raiseTarget}
                      onChangeText={(v) => setField('raiseTarget', v)}
                      keyboardType="number-pad"
                      mono
                    />
                  </View>
                </View>
                <Field
                  label="Monthly sales &amp; marketing spend"
                  prefix="$"
                  placeholder="40000"
                  value={profile.marketingSpend}
                  onChangeText={(v) => setField('marketingSpend', v)}
                  keyboardType="number-pad"
                  mono
                  hint="Everything spent winning customers, including the salaries of the people doing it."
                />
              </View>
            </View>
          ) : null}

          {step === 3 ? (
            <View>
              <Eyebrow>CUSTOMERS</Eyebrow>
              <TxtSemi className="mb-1 mt-2 text-[23px]" style={{ letterSpacing: -0.7 }}>
                Does the maths work?
              </TxtSemi>
              <Txt className="mb-[22px] text-[13px] text-ink-dim" style={{ lineHeight: 20 }}>
                Four numbers. We work out lifetime value and payback from them, so you do not have to.
              </Txt>
              <View className="gap-4">
                <Field
                  label="Active customers"
                  placeholder="180"
                  value={profile.customers}
                  onChangeText={(v) => setField('customers', v)}
                  keyboardType="number-pad"
                  mono
                />
                <View className="flex-row gap-[10px]">
                  <View className="flex-1">
                    <Field
                      label="Revenue per customer"
                      prefix="$"
                      suffix="/mo"
                      placeholder="270"
                      value={profile.arpu}
                      onChangeText={(v) => setField('arpu', v)}
                      keyboardType="number-pad"
                      mono
                    />
                  </View>
                  <View className="flex-1">
                    <Field
                      label="Monthly churn"
                      suffix="%"
                      placeholder="3"
                      value={profile.churn}
                      onChangeText={(v) => setField('churn', v)}
                      keyboardType="decimal-pad"
                      mono
                    />
                  </View>
                </View>
                <Field
                  label="Cost to win a customer"
                  prefix="$"
                  placeholder="320"
                  value={profile.cac}
                  onChangeText={(v) => setField('cac', v)}
                  keyboardType="number-pad"
                  mono
                  hint="Include the sales and marketing effort actually used, not just ad spend."
                />
                <View className="flex-row gap-[10px]">
                  <View className="flex-1">
                    <Field
                      label="Monthly active users"
                      placeholder="2400"
                      value={profile.activeUsers}
                      onChangeText={(v) => setField('activeUsers', v)}
                      keyboardType="number-pad"
                      mono
                      hint="Leave blank if you only count paying customers."
                    />
                  </View>
                  <View className="flex-1">
                    <Field
                      label="Pilots or LOIs"
                      placeholder="3"
                      value={profile.pilots}
                      onChangeText={(v) => setField('pilots', v)}
                      keyboardType="number-pad"
                      mono
                      hint="Signed, but not paying yet."
                    />
                  </View>
                </View>
                <Field
                  label="Revenue share from your biggest customer"
                  suffix="%"
                  placeholder="35"
                  value={profile.customerConcentration}
                  onChangeText={(v) => setField('customerConcentration', v)}
                  keyboardType="number-pad"
                  mono
                  hint="Concentration is a risk an acquirer will price."
                />
                <RatioRow />
              </View>
            </View>
          ) : null}

          {step === 4 ? (
            <View>
              <Eyebrow>MARKET &amp; PLAN</Eyebrow>
              <TxtSemi className="mb-1 mt-2 text-[23px]" style={{ letterSpacing: -0.7 }}>
                What is the opportunity?
              </TxtSemi>
              <Txt className="mb-[22px] text-[13px] text-ink-dim" style={{ lineHeight: 20 }}>
                All optional, and all worth answering. These are what the audit quotes back when it
                explains a verdict — numbers alone only ever produce a score.
              </Txt>
              <View className="gap-4">
                <Field
                  label="How big is the market you can serve today?"
                  placeholder="~18,000 licensed processors in Nigeria; we can serve the 400 already on our rails."
                  value={profile.marketSize}
                  onChangeText={(v) => setField('marketSize', v)}
                  multiline
                  hint="Not the global figure — the slice you could realistically reach, and how you worked it out."
                />
                <Field
                  label="Who else solves this for your customers?"
                  placeholder="Mostly spreadsheets, and one incumbent's reconciliation add-on."
                  value={profile.competition}
                  onChangeText={(v) => setField('competition', v)}
                  multiline
                  hint="Including &quot;they do it by hand&quot; — that is a competitor."
                />
                <Field
                  label="What is limiting growth right now?"
                  placeholder="We can only onboard 6 processors a month — integration is manual."
                  value={profile.growthConstraint}
                  onChangeText={(v) => setField('growthConstraint', v)}
                  multiline
                  hint="The one thing that would move the number most if it were fixed."
                />
                <Field
                  label="What would new capital buy?"
                  placeholder="Two integration engineers, to cut onboarding from 3 weeks to 3 days."
                  value={profile.useOfFunds}
                  onChangeText={(v) => setField('useOfFunds', v)}
                  multiline
                  hint="Map it to the constraint above. Vague answers score badly because they cannot be checked."
                />
              </View>
            </View>
          ) : null}

          {step === 5 ? (
            <View>
              <Eyebrow>TEAM &amp; OWNERSHIP</Eyebrow>
              <TxtSemi className="mb-1 mt-2 text-[23px]" style={{ letterSpacing: -0.7 }}>
                Who is building it?
              </TxtSemi>
              <Txt className="mb-[22px] text-[13px] text-ink-dim" style={{ lineHeight: 20 }}>
                Last step. The ownership questions are quick, and they decide whether the business
                could ever be sold.
              </Txt>
              <View className="gap-5">
                <View className="flex-row gap-[10px]">
                  <View className="flex-1">
                    <Field
                      label="Founders"
                      placeholder="2"
                      value={profile.founders}
                      onChangeText={(v) => setField('founders', v)}
                      keyboardType="number-pad"
                      mono
                    />
                  </View>
                  <View className="flex-1">
                    <Field
                      label="Full time"
                      placeholder="2"
                      value={profile.foundersFullTime}
                      onChangeText={(v) => setField('foundersFullTime', v)}
                      keyboardType="number-pad"
                      mono
                    />
                  </View>
                </View>

                <Field
                  label="People in the company"
                  placeholder="7"
                  value={profile.teamSize}
                  onChangeText={(v) => setField('teamSize', v)}
                  keyboardType="number-pad"
                  mono
                  hint="Everyone, not just founders."
                />

                <View className="gap-[9px]">
                  <FieldLabel>Does the company own the work its people built?</FieldLabel>
                  <OptionGrid
                    options={['Yes', 'No'] as const}
                    value={profile.ipOwned}
                    onChange={(v) => setField('ipOwned', v)}
                  />
                </View>

                <View className="gap-[9px]">
                  <FieldLabel>Would customer contracts survive a change of owner?</FieldLabel>
                  <OptionGrid
                    options={['Yes', 'No'] as const}
                    value={profile.contractsTransferable}
                    onChange={(v) => setField('contractsTransferable', v)}
                  />
                </View>

                <Field
                  label="What can only you do?"
                  placeholder="Sales relationships, the pricing calls, anything nobody else could pick up."
                  value={profile.keyPersonDependency}
                  onChangeText={(v) => setField('keyPersonDependency', v)}
                  multiline
                  hint="Optional, and honest answers score better than empty ones."
                />

                <Field
                  label="What have the founders done before?"
                  placeholder="Led payments integrations at Interswitch for 4 years."
                  value={profile.founderExperience}
                  onChangeText={(v) => setField('founderExperience', v)}
                  multiline
                  hint="Specific and checkable beats &quot;deep fintech experience&quot;."
                />

                <View className="gap-[7px]">
                  <FieldLabel>Is it getting cheaper to serve each customer?</FieldLabel>
                  <OptionGrid
                    options={COST_TRENDS}
                    value={profile.deliveryCostTrend}
                    onChange={(v) => setField('deliveryCostTrend', v)}
                    columns={3}
                  />
                  <Txt className="text-[11px] text-ink-faint">
                    The direction matters more than the number — it separates a business that scales
                    from one that only grows.
                  </Txt>
                </View>

                <Field
                  label="Who owns what"
                  placeholder="Founders 70%, angels 12%, ESOP 18%"
                  value={profile.capTable}
                  onChangeText={(v) => setField('capTable', v)}
                  multiline
                  hint="A summary line is enough."
                />

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
        <Button label={step === 5 ? 'Run AI assessment' : 'Continue'} height={50} onPress={next} />
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
