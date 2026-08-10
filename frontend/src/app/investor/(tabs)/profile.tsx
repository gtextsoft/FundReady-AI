import { useEffect } from 'react';
import { ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppearanceControl } from '@/components/appearance-control';
import { Button } from '@/components/ui/button';
import { Eyebrow, Mono, Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { useThemeColors } from '@/theme/use-theme-colors';
import type { Interest } from '@/domain/interest';
import type { VerificationStatus } from '@/domain/types';
import { initials } from '@/lib/format';
import { route, SIGN_IN } from '@/lib/routes';
import { useInvestor } from '@/store/investor';
import { useSession } from '@/store/session';

const VERIFICATION_COPY: Record<VerificationStatus, { label: string; color: string }> = {
  unverified: { label: 'Not verified', color: C.amb },
  in_review: { label: 'In review', color: C.blue },
  verified: { label: 'Verified', color: C.grn },
  rejected: { label: 'Rejected', color: C.red },
};

const INTEREST_LABEL: Record<Interest['status'], string> = {
  pending: 'Pending review',
  approved: 'Approved',
  declined: 'Declined',
  withdrawn: 'Withdrawn',
};

export default function InvestorProfile() {
  const colors = useThemeColors();
  const insets = useSafeAreaInsets();
  const session = useSession((s) => s.session);
  const account = useSession((s) => s.investorAccount);
  const signOut = useSession((s) => s.signOut);
  const watchlist = useInvestor((s) => s.watchlist);
  const interests = useInvestor((s) => s.interests);
  const loadInterests = useInvestor((s) => s.loadInterests);

  useEffect(() => {
    void loadInterests();
  }, [loadInterests]);

  const status = account?.verification ?? 'unverified';
  const verification = VERIFICATION_COPY[status];

  async function out() {
    await signOut();
    router.replace(SIGN_IN);
  }

  return (
    <ScrollView
      className="flex-1 bg-ground"
      contentContainerStyle={{ paddingTop: insets.top + 8, paddingHorizontal: 18, paddingBottom: 24 }}
      showsVerticalScrollIndicator={false}>
      <TxtSemi className="mb-4 text-[19px]" style={{ letterSpacing: -0.5 }}>
        Profile
      </TxtSemi>

      <View className="flex-row items-center gap-3 rounded-[12px] border border-line bg-surface-1 p-[14px]">
        <View className="h-[44px] w-[44px] items-center justify-center rounded-full border border-line-strong bg-surface-3">
          <TxtSemi className="text-[14px] text-ink-muted">
            {session?.displayName ? initials(session.displayName) : 'IN'}
          </TxtSemi>
        </View>
        <View className="flex-1">
          <TxtSemi className="text-[15px]">{session?.displayName ?? 'Investor'}</TxtSemi>
          {account?.credentials?.firm ? (
            <Txt className="text-[12px] text-ink-muted">{account.credentials.firm}</Txt>
          ) : null}
          <Txt className="text-[12px] text-ink-dim">{session?.email ?? 'not signed in'}</Txt>
        </View>
        <View className="rounded-[5px] border border-line-strong px-2 py-[3px]">
          <Mono className="text-[9.5px]" style={{ color: colors.inkMuted }}>
            INVESTOR
          </Mono>
        </View>
      </View>

      <View className="mt-[9px] rounded-[12px] border border-line bg-surface-1 p-[14px]">
        <AppearanceControl />
      </View>

      {!account?.emailVerified ? (
        <View className="mt-[9px] rounded-[11px] border border-line bg-surface-1 p-[14px]">
          <TxtMed className="text-[13px]">Confirm your email</TxtMed>
          <Txt className="mt-1 text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
            Discovery and interest require a confirmed address.
          </Txt>
          <View className="mt-3">
            <Button
              label="Confirm email"
              height={40}
              onPress={() =>
                router.push(
                  route(
                    `/verify-email?email=${encodeURIComponent(session?.email ?? '')}&next=investor`,
                  ),
                )
              }
            />
          </View>
        </View>
      ) : null}

      <View className="mt-[9px] flex-row gap-[9px]">
        <Stat label="WATCHING" value={watchlist.length} />
        <Stat label="INTERESTS" value={interests.length} />
      </View>

      <Eyebrow className="mb-[10px] mt-6">MY INTERESTS</Eyebrow>
      {interests.length === 0 ? (
        <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
          <Txt className="text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
            When you express interest from dealflow, FundReady AI reviews it here. Approval is not a
            report reveal — that is a separate admin step.
          </Txt>
        </View>
      ) : (
        <View className="gap-[9px]">
          {interests.map((i) => (
            <View key={i.id} className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
              <View className="flex-row items-center justify-between">
                <Mono className="text-[10px] text-ink-faint" numberOfLines={1}>
                  {i.startupId.slice(0, 8)}…
                </Mono>
                <Mono className="text-[10px]" style={{ color: C.inkMuted }}>
                  {INTEREST_LABEL[i.status]}
                </Mono>
              </View>
              {i.note ? (
                <Txt className="mt-2 text-[12px] text-ink-dim" numberOfLines={2}>
                  {i.note}
                </Txt>
              ) : null}
              {i.revealedRunIds.length > 0 ? (
                <Txt className="mt-2 text-[11px]" style={{ color: C.grn }}>
                  {i.revealedRunIds.length} report
                  {i.revealedRunIds.length === 1 ? '' : 's'} revealed
                </Txt>
              ) : null}
              <View className="mt-2">
                <Button
                  label="Open summary"
                  variant="secondary"
                  height={36}
                  onPress={() => router.push(route(`/investor/company/${i.startupId}`))}
                />
              </View>
            </View>
          ))}
        </View>
      )}

      <Eyebrow className="mb-[10px] mt-6">VERIFICATION</Eyebrow>
      <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
        <View className="flex-row items-center justify-between">
          <TxtMed className="text-[13.5px]">Investor status</TxtMed>
          <View className="flex-row items-center gap-2">
            <View className="h-[6px] w-[6px] rounded-full" style={{ backgroundColor: verification.color }} />
            <Mono className="text-[11px]" style={{ color: verification.color }}>
              {verification.label}
            </Mono>
          </View>
        </View>
        <Txt className="mt-2 text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
          {status === 'verified'
            ? `${account?.credentials?.investorType ?? 'Investor'} · ${account?.credentials?.country ?? ''}`.trim()
            : 'Identity verification (Stripe Identity) is not live yet. You can already browse and express interest after confirming email.'}
        </Txt>
        {status !== 'verified' ? (
          <Txt className="mt-3 text-[11.5px] text-ink-faint" style={{ lineHeight: 17 }}>
            We will prompt you here when identity verification opens.
          </Txt>
        ) : null}
      </View>

      <View className="mt-6">
        <Button label="Sign out" variant="secondary" onPress={out} />
      </View>
    </ScrollView>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <View className="flex-1 rounded-[11px] border border-line bg-surface-1 px-[13px] py-3">
      <Txt className="text-[9.5px] text-ink-faint" style={{ letterSpacing: 0.5 }}>
        {label}
      </Txt>
      <Mono className="mt-1 text-[18px]">{value}</Mono>
    </View>
  );
}
