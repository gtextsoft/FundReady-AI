import { ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Eyebrow, Mono, Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import type { VerificationStatus } from '@/domain/types';
import { initials } from '@/lib/format';
import { route, SIGN_IN } from '@/lib/routes';
import { useInvestor } from '@/store/investor';
import { useSession } from '@/store/session';

const VERIFICATION_COPY: Record<VerificationStatus, { label: string; color: string }> = {
  unverified: { label: 'Not verified', color: C.flag },
  in_review: { label: 'In review', color: C.info },
  verified: { label: 'Verified', color: C.signal },
  rejected: { label: 'Rejected', color: C.alert },
};

export default function InvestorProfile() {
  const insets = useSafeAreaInsets();
  const session = useSession((s) => s.session);
  const account = useSession((s) => s.investorAccount);
  const signOut = useSession((s) => s.signOut);
  const watchlist = useInvestor((s) => s.watchlist);
  const introRequested = useInvestor((s) => s.introRequested);

  const status = account?.verification ?? 'unverified';
  const verification = VERIFICATION_COPY[status];

  async function out() {
    await signOut();
    router.replace(SIGN_IN);
  }

  return (
    <ScrollView
      className="flex-1 bg-obsidian"
      contentContainerStyle={{ paddingTop: insets.top + 8, paddingHorizontal: 18, paddingBottom: 24 }}
      showsVerticalScrollIndicator={false}>
      <TxtSemi className="mb-4 text-[19px]" style={{ letterSpacing: -0.5 }}>
        Profile
      </TxtSemi>

      <View className="flex-row items-center gap-3 rounded-[12px] border border-graphite bg-carbon-low p-[14px]">
        <View className="h-[44px] w-[44px] items-center justify-center rounded-full border border-graphite-strong bg-carbon-high">
          <TxtSemi className="text-[14px] text-bone-secondary">
            {session?.displayName ? initials(session.displayName) : 'IN'}
          </TxtSemi>
        </View>
        <View className="flex-1">
          {/* The person first; the firm is context, and may not exist yet. */}
          <TxtSemi className="text-[15px]">{session?.displayName ?? 'Investor'}</TxtSemi>
          {account?.credentials?.firm ? (
            <Txt className="text-[12px] text-bone-secondary">{account.credentials.firm}</Txt>
          ) : null}
          <Txt className="text-[12px] text-bone-muted">{session?.email ?? 'not signed in'}</Txt>
        </View>
        <View className="rounded-[5px] border border-graphite-strong px-2 py-[3px]">
          <Mono className="text-[9.5px]" style={{ color: C.boneSecondary }}>
            INVESTOR
          </Mono>
        </View>
      </View>

      <View className="mt-[9px] flex-row gap-[9px]">
        <Stat label="WATCHING" value={watchlist.length} />
        <Stat label="INTROS REQUESTED" value={introRequested.length} />
      </View>

      <Eyebrow className="mb-[10px] mt-6">VERIFICATION</Eyebrow>
      <View className="rounded-[12px] border border-graphite bg-carbon-low p-[14px]">
        <View className="flex-row items-center justify-between">
          <TxtMed className="text-[13.5px]">Investor status</TxtMed>
          <View className="flex-row items-center gap-2">
            <View className="h-[6px] w-[6px] rounded-full" style={{ backgroundColor: verification.color }} />
            <Mono className="text-[11px]" style={{ color: verification.color }}>
              {verification.label}
            </Mono>
          </View>
        </View>
        <Txt className="mt-2 text-[12px] text-bone-secondary" style={{ lineHeight: 18 }}>
          {status === 'verified'
            ? `${account?.credentials?.investorType ?? 'Investor'} · ${account?.credentials?.country ?? ''}`.trim()
            : 'Founders only receive introductions and calls from verified investors. It takes a minute.'}
        </Txt>
        {status !== 'verified' ? (
          <View className="mt-3">
            <Button label="Verify your profile" height={42} onPress={() => router.push(route('/investor/verify'))} />
          </View>
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
    <View className="flex-1 rounded-[11px] border border-graphite bg-carbon-low px-[13px] py-3">
      <Txt className="text-[9.5px] text-bone-faint" style={{ letterSpacing: 0.5 }}>
        {label}
      </Txt>
      <Mono className="mt-1 text-[18px]">{value}</Mono>
    </View>
  );
}
