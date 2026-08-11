import { useCallback, useEffect, useState } from 'react';
import { Linking, Pressable, ScrollView, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Chip } from '@/components/ui/controls';
import { Field } from '@/components/ui/field';
import { Select } from '@/components/ui/select';
import { Eyebrow, Mono, Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { Unavailable } from '@/components/unavailable';
import { api } from '@/api';
import type { ServerStage } from '@/api/profile-mapping';
import { INVESTOR_TYPES, SECTORS, type VerificationStatus } from '@/domain/types';
import { C } from '@/theme/tokens';
import { useSession } from '@/store/session';

const COUNTRIES = [
  { code: 'NG', label: 'Nigeria' },
  { code: 'GH', label: 'Ghana' },
  { code: 'KE', label: 'Kenya' },
  { code: 'ZA', label: 'South Africa' },
  { code: 'GB', label: 'United Kingdom' },
  { code: 'US', label: 'United States' },
  { code: 'AE', label: 'United Arab Emirates' },
] as const;

const STAGE_OPTIONS: { value: ServerStage; label: string }[] = [
  { value: 'pre_seed', label: 'Pre-seed' },
  { value: 'seed', label: 'Seed' },
  { value: 'series_a', label: 'Series A' },
  { value: 'growth', label: 'Growth' },
];

const GEO_OPTIONS = ['NG', 'GH', 'KE', 'ZA', 'GB', 'US', 'AE', 'EU', 'AF'];

const STATUS_COPY: Record<VerificationStatus, { label: string; color: string; body: string }> = {
  unverified: {
    label: 'Not started',
    color: C.amb,
    body: 'Save your thesis, then open identity verification in the browser.',
  },
  in_review: {
    label: 'In review',
    color: C.blue,
    body: 'Stripe is reviewing your documents. This screen refreshes when you return.',
  },
  verified: {
    label: 'Verified',
    color: C.grn,
    body: 'You can express interest and propose calls on dealflow.',
  },
  rejected: {
    label: 'Failed',
    color: C.red,
    body: 'Verification did not pass. You can start a new session below.',
  },
};

function toggle<T extends string>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((x) => x !== value) : [...list, value];
}

/**
 * Investor credentials, thesis, and Stripe Identity hand-off.
 */
export default function VerifyInvestor() {
  const insets = useSafeAreaInsets();
  const account = useSession((s) => s.investorAccount);
  const refreshAccount = useSession((s) => s.refreshAccount);
  const setInvestorAccount = useSession((s) => s.setInvestorAccount);

  const [firm, setFirm] = useState('');
  const [investorType, setInvestorType] = useState('');
  const [countryLabel, setCountryLabel] = useState('Nigeria');
  const [linkedinUrl, setLinkedinUrl] = useState('');
  const [sectors, setSectors] = useState<string[]>([]);
  const [stages, setStages] = useState<ServerStage[]>([]);
  const [geographies, setGeographies] = useState<string[]>([]);
  const [ticketMin, setTicketMin] = useState('');
  const [ticketMax, setTicketMax] = useState('');
  const [currency, setCurrency] = useState('USD');
  const [riskNotes, setRiskNotes] = useState('');
  const [kycStatus, setKycStatus] = useState(account?.verification ?? 'unverified');

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<'save' | 'kyc' | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [profile, accountFresh] = await Promise.all([
        api.getInvestorProfile(),
        api.getInvestorAccount(),
      ]);
      setInvestorAccount(accountFresh);
      setFirm(profile.firm);
      setInvestorType(profile.investorType);
      const match = COUNTRIES.find((c) => c.code === profile.country.toUpperCase());
      setCountryLabel(match?.label ?? (profile.country ? profile.country : 'Nigeria'));
      setLinkedinUrl(profile.linkedinUrl);
      setSectors(profile.thesisSectors);
      setStages(profile.thesisStages.filter((s): s is ServerStage => STAGE_OPTIONS.some((o) => o.value === s)));
      setGeographies(profile.thesisGeographies);
      setTicketMin(
        profile.ticketMinMinor != null ? String(Math.round(profile.ticketMinMinor / 100)) : '',
      );
      setTicketMax(
        profile.ticketMaxMinor != null ? String(Math.round(profile.ticketMaxMinor / 100)) : '',
      );
      setCurrency(profile.ticketCurrency ?? 'USD');
      setRiskNotes(profile.riskNotes);
      setKycStatus(accountFresh.verification);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [setInvestorAccount]);

  useEffect(() => {
    void load();
  }, [load]);

  useFocusEffect(
    useCallback(() => {
      void refreshAccount().then(() => {
        const next = useSession.getState().investorAccount?.verification;
        if (next) setKycStatus(next);
      });
    }, [refreshAccount]),
  );

  const status = STATUS_COPY[kycStatus];

  async function saveProfile() {
    setBusy('save');
    setError(null);
    setSaved(false);
    try {
      const country = COUNTRIES.find((c) => c.label === countryLabel)?.code ?? countryLabel.slice(0, 2);
      const min = ticketMin.trim() ? Math.round(Number(ticketMin) * 100) : null;
      const max = ticketMax.trim() ? Math.round(Number(ticketMax) * 100) : null;
      if (ticketMin.trim() && Number.isNaN(min)) throw new Error('Cheque minimum must be a number.');
      if (ticketMax.trim() && Number.isNaN(max)) throw new Error('Cheque maximum must be a number.');

      await api.upsertInvestorProfile({
        firm,
        investorType,
        country,
        linkedinUrl,
        thesisSectors: sectors,
        thesisStages: stages,
        thesisGeographies: geographies,
        ticketMinMinor: min,
        ticketMaxMinor: max,
        ticketCurrency: currency,
        riskNotes,
      });
      const accountFresh = await api.getInvestorAccount();
      setInvestorAccount(accountFresh);
      setKycStatus(accountFresh.verification);
      setSaved(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  async function openKyc() {
    setBusy('kyc');
    setError(null);
    try {
      // Persist thesis first so SACI has firm details before Identity returns.
      const country = COUNTRIES.find((c) => c.label === countryLabel)?.code ?? countryLabel.slice(0, 2);
      const min = ticketMin.trim() ? Math.round(Number(ticketMin) * 100) : null;
      const max = ticketMax.trim() ? Math.round(Number(ticketMax) * 100) : null;
      await api.upsertInvestorProfile({
        firm,
        investorType,
        country,
        linkedinUrl,
        thesisSectors: sectors,
        thesisStages: stages,
        thesisGeographies: geographies,
        ticketMinMinor: Number.isNaN(min as number) ? null : min,
        ticketMaxMinor: Number.isNaN(max as number) ? null : max,
        ticketCurrency: currency,
        riskNotes,
      });
      const session = await api.startInvestorKyc();
      setKycStatus(
        session.kycStatus === 'pending'
          ? 'in_review'
          : session.kycStatus === 'verified'
            ? 'verified'
            : session.kycStatus === 'failed'
              ? 'rejected'
              : 'unverified',
      );
      await Linking.openURL(session.url);
      await refreshAccount();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  return (
    <View className="flex-1 bg-ground">
      <View className="border-b border-line-soft px-[18px] pb-3" style={{ paddingTop: insets.top + 4 }}>
        <View className="h-[34px] flex-row items-center justify-between">
          <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={10}>
            <Txt className="text-[19px] text-ink">←</Txt>
          </Pressable>
          <Mono className="text-[10px] text-ink-faint" style={{ letterSpacing: 1.2 }}>
            INVESTOR VERIFICATION
          </Mono>
          <View className="w-5" />
        </View>
      </View>

      <ScrollView
        className="flex-1"
        contentContainerStyle={{ padding: 18, paddingBottom: insets.bottom + 28, gap: 14 }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}>
        <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
          <View className="flex-row items-center justify-between">
            <TxtMed className="text-[13.5px]">Identity status</TxtMed>
            <View className="flex-row items-center gap-2">
              <View className="h-[6px] w-[6px] rounded-full" style={{ backgroundColor: status.color }} />
              <Mono className="text-[11px]" style={{ color: status.color }}>
                {status.label}
              </Mono>
            </View>
          </View>
          <Txt className="mt-2 text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
            {status.body}
          </Txt>
        </View>

        {error ? <Unavailable title="Could not update verification" error={error} /> : null}

        {loading ? (
          <Txt className="text-[12.5px] text-ink-muted">Loading your profile…</Txt>
        ) : (
          <>
            <Eyebrow>CREDENTIALS</Eyebrow>
            <Field label="Firm / fund" value={firm} onChangeText={setFirm} placeholder="Acme Ventures" />
            <Select
              label="Investor type"
              value={investorType}
              placeholder="Select type"
              options={INVESTOR_TYPES}
              onChange={setInvestorType}
            />
            <Select
              label="Country"
              value={countryLabel}
              placeholder="Select country"
              options={COUNTRIES.map((c) => c.label)}
              onChange={setCountryLabel}
            />
            <Field
              label="LinkedIn URL"
              value={linkedinUrl}
              onChangeText={setLinkedinUrl}
              placeholder="https://linkedin.com/in/…"
              autoCapitalize="none"
              autoCorrect={false}
            />

            <Eyebrow className="mt-2">THESIS</Eyebrow>
            <Txt className="text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
              Sectors
            </Txt>
            <View className="flex-row flex-wrap gap-[7px]">
              {SECTORS.map((s) => (
                <Chip key={s} label={s} selected={sectors.includes(s)} onPress={() => setSectors(toggle(sectors, s))} />
              ))}
            </View>

            <Txt className="mt-1 text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
              Stages
            </Txt>
            <View className="flex-row flex-wrap gap-[7px]">
              {STAGE_OPTIONS.map((s) => (
                <Chip
                  key={s.value}
                  label={s.label}
                  selected={stages.includes(s.value)}
                  onPress={() => setStages(toggle(stages, s.value))}
                />
              ))}
            </View>

            <Txt className="mt-1 text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
              Geographies
            </Txt>
            <View className="flex-row flex-wrap gap-[7px]">
              {GEO_OPTIONS.map((g) => (
                <Chip
                  key={g}
                  label={g}
                  selected={geographies.includes(g)}
                  onPress={() => setGeographies(toggle(geographies, g))}
                />
              ))}
            </View>

            <View className="flex-row gap-[9px]">
              <View className="flex-1">
                <Field
                  label="Cheque min"
                  value={ticketMin}
                  onChangeText={setTicketMin}
                  placeholder="50000"
                  keyboardType="numeric"
                  mono
                />
              </View>
              <View className="flex-1">
                <Field
                  label="Cheque max"
                  value={ticketMax}
                  onChangeText={setTicketMax}
                  placeholder="250000"
                  keyboardType="numeric"
                  mono
                />
              </View>
            </View>
            <Txt className="text-[11px] text-ink-faint">
              Whole currency units (e.g. 50000 for 50,000). Stored as minor units on the server.
            </Txt>
            <Select
              label="Currency"
              value={currency}
              placeholder="USD"
              options={['USD', 'GBP', 'EUR', 'NGN']}
              onChange={setCurrency}
            />
            <Field
              label="Risk notes (optional)"
              value={riskNotes}
              onChangeText={setRiskNotes}
              placeholder="Exclusions, cheque-size caveats…"
            />

            {saved ? (
              <TxtSemi className="text-[13px]" style={{ color: C.grn }}>
                Thesis saved
              </TxtSemi>
            ) : null}

            <Button
              label="Save thesis"
              variant="secondary"
              loading={busy === 'save'}
              disabled={busy !== null}
              onPress={saveProfile}
            />

            {kycStatus !== 'verified' ? (
              <Button
                label={kycStatus === 'in_review' ? 'Continue identity verification' : 'Verify identity with Stripe'}
                loading={busy === 'kyc'}
                disabled={busy !== null}
                onPress={openKyc}
              />
            ) : (
              <View className="rounded-[11px] border border-line bg-surface-1 p-[14px]">
                <TxtSemi className="text-[14px]" style={{ color: C.grn }}>
                  Identity verified
                </TxtSemi>
                <Txt className="mt-1 text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
                  You can return to dealflow and express interest.
                </Txt>
              </View>
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}
