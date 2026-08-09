import { useCallback } from 'react';
import { Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ModuleTile } from '@/components/founder/module-tile';
import { StatusBanner } from '@/components/founder/status-banner';
import { Mark } from '@/components/ui/mark';
import { Eyebrow, Mono, Txt, TxtSemi } from '@/components/ui/text';
import { C, band } from '@/theme/tokens';
import { gate, hasAccess, isPaid, type Gate } from '@/domain/access';
import type { FounderAccount } from '@/domain/types';
import { route, VERIFY_EMAIL } from '@/lib/routes';
import { useFounder } from '@/store/founder';
import { useNotifications } from '@/store/notifications';
import { useSession } from '@/store/session';

const ALLOWED: Gate = { allowed: true, reason: null };

/** Home. Everything the founder can reach, with locks shown rather than hidden. */
export default function FounderDashboard() {
  const insets = useSafeAreaInsets();

  const session = useSession((s) => s.session);
  const account = useSession((s) => s.founderAccount);
  const refreshAccount = useSession((s) => s.refreshAccount);

  const assessment = useFounder((s) => s.assessment);
  const profile = useFounder((s) => s.profile);

  const loadNotifications = useNotifications((s) => s.load);
  const unread = useNotifications((s) => s.unreadCount());
  const pendingCalls = useNotifications((s) => s.pendingCalls().length);

  // Verification and billing state change server-side, so re-read on focus.
  useFocusEffect(
    useCallback(() => {
      refreshAccount();
      loadNotifications('founder');
    }, [refreshAccount, loadNotifications]),
  );

  if (!account) return <View className="flex-1 bg-ground" />;

  const locked = !hasAccess(account);
  const paid = isPaid(account);
  const companyName = profile.company || account.companyName || 'Your company';

  // Computed from `account` on every render so the compiler re-derives them
  // when verification or payment state changes. See the note in store/session.
  const canAiMentor = gate(account, 'aiMentor');
  const canRequests = gate(account, 'investorRequests');
  const canProgrammes = gate(account, 'programmes');
  const canReassess = gate(account, 'reassess');

  const goPaywall = () => router.push(route('/founder/paywall'));
  const goVerify = () => router.push(route('/founder/verify'));
  const goConfirmEmail = () => router.push(VERIFY_EMAIL);

  /** A locked module routes to whatever would unlock it, not to a dead end. */
  const openGated = (gate: Gate, destination: string) => () => {
    if (gate.allowed) router.push(route(destination));
    else if (gate.reason === 'email') goConfirmEmail();
    else if (gate.reason === 'payment') goPaywall();
    else goVerify();
  };

  return (
    <ScrollView
      className="flex-1 bg-ground"
      contentContainerStyle={{ paddingTop: insets.top + 4, paddingHorizontal: 18, paddingBottom: 24 }}
      showsVerticalScrollIndicator={false}
      refreshControl={<RefreshControl refreshing={false} onRefresh={refreshAccount} tintColor={C.inkFaint} />}>
      {/* header */}
      <View className="h-[34px] flex-row items-center justify-between">
        <View className="flex-row items-center gap-2">
          <Mark size={16} />
          <TxtSemi className="text-[15px]" style={{ letterSpacing: -0.3 }}>
            {companyName}
          </TxtSemi>
        </View>
        <View className="flex-row items-center gap-[10px]">
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={unread ? `Alerts, ${unread} unread` : 'Alerts'}
            onPress={() => router.push(route('/founder/alerts'))}
            className="h-[30px] w-[30px] items-center justify-center rounded-[8px] border border-line">
            <Txt className="text-[12px] text-ink-muted">◔</Txt>
            {unread > 0 ? (
              <View
                className="absolute -right-[3px] -top-[3px] h-[13px] min-w-[13px] items-center justify-center rounded-full px-[3px]"
                style={{ backgroundColor: C.blue }}>
                <Mono className="text-[8px] text-white">{unread > 9 ? '9+' : unread}</Mono>
              </View>
            ) : null}
          </Pressable>
          <View className="h-[28px] w-[28px] items-center justify-center rounded-full bg-line">
            <TxtSemi className="text-[10px] text-ink-muted">
              {(session?.displayName ?? 'F').slice(0, 2).toUpperCase()}
            </TxtSemi>
          </View>
        </View>
      </View>

      <View className="mt-3">
        <StatusBanner
          account={account}
          onUnlock={goPaywall}
          onVerify={goVerify}
          onConfirmEmail={goConfirmEmail}
        />
      </View>

      {/* fundability */}
      <Eyebrow className="mb-[10px] mt-6">FUNDABILITY</Eyebrow>
      <ScoreCard account={account} score={assessment?.score ?? null} />

      {/* modules */}
      <Eyebrow className="mb-[10px] mt-6">YOUR TOOLS</Eyebrow>
      <View className="flex-row flex-wrap gap-[9px]">
        <ModuleTile
          glyph="✦"
          title="AI mentor"
          subtitle="Ask anything about your metrics"
          gate={canAiMentor}
          onPress={openGated(canAiMentor, '/founder/ai-mentor')}
        />
        <ModuleTile
          glyph="◈"
          title="Investor interest"
          subtitle={pendingCalls ? `${pendingCalls} awaiting your answer` : 'Intros and call requests'}
          gate={canRequests}
          badge={pendingCalls}
          onPress={openGated(canRequests, '/founder/investors')}
        />
        <ModuleTile
          glyph="◎"
          title="Programmes"
          subtitle="Readiness & Wealth Creation"
          gate={canProgrammes}
          onPress={openGated(canProgrammes, '/founder/programmes')}
        />
        <ModuleTile
          glyph="⟳"
          title="Re-assess"
          subtitle="Update your metrics and re-score"
          gate={canReassess}
          onPress={openGated(canReassess, '/onboarding')}
        />
        <ModuleTile
          glyph="⎘"
          title="Assessment"
          subtitle={profile.deck ? profile.deck : 'No deck on file'}
          gate={ALLOWED}
          onPress={() => router.push(route('/onboarding'))}
        />
        <ModuleTile
          glyph="◇"
          title={paid ? 'Your plan' : locked ? 'Unlock access' : 'Trial'}
          subtitle={paid ? 'Unlocked — one-off payment' : 'Manage your access'}
          gate={ALLOWED}
          onPress={goPaywall}
        />
      </View>
    </ScrollView>
  );
}

function ScoreCard({ account, score }: { account: FounderAccount; score: number | null }) {
  if (score === null) {
    return (
      <Pressable
        accessibilityRole="button"
        onPress={() => router.push(route('/onboarding'))}
        className="rounded-[12px] border border-line bg-surface-1 p-[16px]">
        <TxtSemi className="text-[14px]">Run your Fundability assessment</TxtSemi>
        <Txt className="mt-[4px] text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
          Four short steps. Investors cannot see you without a score.
        </Txt>
        <Txt className="mt-3 text-[12.5px]" style={{ color: C.blue }}>
          Start assessment →
        </Txt>
      </Pressable>
    );
  }

  const b = band(score);
  const visible = account.verification === 'verified' && hasAccess(account);

  return (
    <Pressable
      accessibilityRole="button"
      onPress={() => router.push(route('/results'))}
      className="flex-row items-center gap-4 rounded-[12px] border border-line bg-surface-1 p-[16px]">
      <View
        className="h-[62px] w-[62px] items-center justify-center rounded-full"
        style={{ borderWidth: 3, borderColor: b.color }}>
        <Mono className="text-[22px]" style={{ letterSpacing: -1 }}>
          {score}
        </Mono>
      </View>
      <View className="flex-1">
        <TxtSemi className="text-[14px]" style={{ color: b.color }}>
          {b.label}
        </TxtSemi>
        <Txt className="mt-[3px] text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
          {visible
            ? 'Investors matching your profile can see this score.'
            : 'Hidden from investors until your company is verified.'}
        </Txt>
      </View>
      <Txt className="text-[13px] text-ink-faint">›</Txt>
    </Pressable>
  );
}
