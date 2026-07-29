import { ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Eyebrow, Mono, Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { daysLeftInTrial, hasAccess } from '@/domain/access';
import { UNLOCK_PRICE } from '@/domain/pricing';
import type { VerificationStatus } from '@/domain/types';
import { __setTrialEndsAt } from '@/api/mock';
import { route, SIGN_IN } from '@/lib/routes';
import { useFounder } from '@/store/founder';
import { useSession } from '@/store/session';

const VERIFICATION_COPY: Record<VerificationStatus, { label: string; color: string }> = {
  unverified: { label: 'Not verified', color: C.amb },
  in_review: { label: 'In review', color: C.blue },
  verified: { label: 'Verified', color: C.grn },
  rejected: { label: 'Rejected', color: C.red },
};

export default function FounderProfile() {
  const insets = useSafeAreaInsets();
  const session = useSession((s) => s.session);
  const account = useSession((s) => s.founderAccount);
  const refreshAccount = useSession((s) => s.refreshAccount);
  const signOut = useSession((s) => s.signOut);
  const resetFounder = useFounder((s) => s.reset);
  const profile = useFounder((s) => s.profile);

  if (!account) return <View className="flex-1 bg-ground" />;

  const verification = VERIFICATION_COPY[account.verification];
  const locked = !hasAccess(account);

  async function out() {
    await signOut();
    resetFounder();
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
            {(session?.displayName ?? 'F').slice(0, 2).toUpperCase()}
          </TxtSemi>
        </View>
        <View className="flex-1">
          <TxtSemi className="text-[15px]">{profile.company || account.companyName || 'Your company'}</TxtSemi>
          <Txt className="text-[12px] text-ink-dim">{session?.email ?? 'not signed in'}</Txt>
        </View>
        <View className="rounded-[5px] border border-line-strong px-2 py-[3px]">
          <Mono className="text-[9.5px]" style={{ color: C.inkMuted }}>
            FOUNDER
          </Mono>
        </View>
      </View>

      {/* verification */}
      <Eyebrow className="mb-[10px] mt-6">COMPANY VERIFICATION</Eyebrow>
      <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
        <View className="flex-row items-center justify-between">
          <TxtMed className="text-[13.5px]">Registration status</TxtMed>
          <View className="flex-row items-center gap-2">
            <View className="h-[6px] w-[6px] rounded-full" style={{ backgroundColor: verification.color }} />
            <Mono className="text-[11px]" style={{ color: verification.color }}>
              {verification.label}
            </Mono>
          </View>
        </View>
        {account.registration ? (
          <Txt className="mt-2 text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
            {account.registration.legalName} · {account.registration.registrationNumber} ·{' '}
            {account.registration.country}
          </Txt>
        ) : (
          <Txt className="mt-2 text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
            Confirm your company is registered in your country to be seen by investors.
          </Txt>
        )}
        {account.verification !== 'verified' && account.verification !== 'in_review' ? (
          <View className="mt-3">
            <Button label="Verify company" height={42} onPress={() => router.push(route('/founder/verify'))} />
          </View>
        ) : null}
      </View>

      {/* access */}
      <Eyebrow className="mb-[10px] mt-6">ACCESS</Eyebrow>
      <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
        <View className="flex-row items-center justify-between">
          <TxtMed className="text-[13.5px]">
            {account.paidAt ? 'Unlocked' : locked ? 'Trial ended' : 'Free trial'}
          </TxtMed>
          <Mono className="text-[11px]" style={{ color: account.paidAt ? C.grn : locked ? C.red : C.amb }}>
            {account.paidAt
              ? `${UNLOCK_PRICE.label} PAID`
              : locked
                ? 'LOCKED'
                : `${daysLeftInTrial(account)} DAYS LEFT`}
          </Mono>
        </View>
        <Txt className="mt-2 text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
          {account.paidAt
            ? 'One-off payment received. Your access does not expire.'
            : 'Full access during the trial. A single one-off payment keeps it permanently.'}
        </Txt>
        {!account.paidAt ? (
          <View className="mt-3">
            <Button
              label={`Unlock for ${UNLOCK_PRICE.label}`}
              height={42}
              onPress={() => router.push(route('/founder/paywall'))}
            />
          </View>
        ) : null}
      </View>

      <View className="mt-6">
        <Button label="Sign out" variant="secondary" onPress={out} />
      </View>

      {/* Developer controls — delete with the mock backend. */}
      {__DEV__ ? (
        <>
          <Eyebrow className="mb-[10px] mt-8">DEVELOPER</Eyebrow>
          <View className="gap-[9px] rounded-[12px] border border-line bg-surface-1 p-[14px]">
            <Txt className="text-[11.5px] text-ink-dim" style={{ lineHeight: 17 }}>
              Move the trial boundary to see both sides of the paywall without waiting two weeks.
            </Txt>
            <Button
              label="Expire trial now"
              variant="secondary"
              height={38}
              onPress={async () => {
                __setTrialEndsAt(new Date(Date.now() - 1000).toISOString());
                await refreshAccount();
              }}
            />
            <Button
              label="Restore 14-day trial"
              variant="secondary"
              height={38}
              onPress={async () => {
                __setTrialEndsAt(new Date(Date.now() + 14 * 86_400_000).toISOString());
                await refreshAccount();
              }}
            />
          </View>
        </>
      ) : null}
    </ScrollView>
  );
}
