import { useEffect, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { ScheduleCallSheet } from '@/components/investor/schedule-call-sheet';
import { Button } from '@/components/ui/button';
import { MetaPill, Segmented } from '@/components/ui/controls';
import { Mono, MonoMed, Txt, TxtSemi } from '@/components/ui/text';
import { C, scoreColor } from '@/theme/tokens';
import { Unavailable } from '@/components/unavailable';
import { api } from '@/api';
import { investorGate } from '@/domain/access';
import type { DiscoveredStartup } from '@/domain/discovery';
import { initials } from '@/lib/format';
import { route } from '@/lib/routes';
import { useInvestor } from '@/store/investor';
import { useSession } from '@/store/session';

type Pane = 'metrics' | 'memo';

const PANES = [
  { value: 'metrics' as Pane, label: 'Metrics' },
  { value: 'memo' as Pane, label: 'AI memo' },
];

export default function CompanyDetail() {
  const insets = useSafeAreaInsets();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [company, setCompany] = useState<DiscoveredStartup | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [pane, setPane] = useState<Pane>('metrics');
  const [introBusy, setIntroBusy] = useState(false);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [callSent, setCallSent] = useState(false);

  const watchlist = useInvestor((s) => s.watchlist);
  const toggleWatch = useInvestor((s) => s.toggleWatch);
  const introRequested = useInvestor((s) => s.introRequested);
  const requestIntro = useInvestor((s) => s.requestIntro);

  const account = useSession((s) => s.investorAccount);
  const verified = account?.verification === 'verified';
  // Absent account means nothing is loaded yet, so assume the most locked state.
  const gate = investorGate(
    account ?? { emailVerified: false, verification: 'unverified', credentials: null },
    'requestIntroduction',
  );

  useEffect(() => {
    let live = true;
    api
      .getDiscoveredStartup(String(id))
      .then((c) => {
        if (!live) return;
        setCompany(c);
        setError(null);
      })
      .catch((e: unknown) => {
        if (!live) return;
        setCompany(null);
        setError(e);
      });
    return () => {
      live = false;
    };
  }, [id]);

  if (error) {
    return (
      <View className="flex-1 bg-obsidian px-[18px]" style={{ paddingTop: insets.top + 16 }}>
        <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={10}>
          <Txt className="mb-4 text-[19px] text-bone">←</Txt>
        </Pressable>
        <Unavailable title="This company could not be loaded" error={error} />
      </View>
    );
  }

  if (!company) return <View className="flex-1 bg-obsidian" />;

  const watched = watchlist.includes(company.startupId);
  const introSent = introRequested.includes(company.startupId);
  const name = company.name ?? 'Unnamed company';
  const fundScore = company.fundability.score;

  async function intro() {
    if (!company || introSent) return;
    if (!gate.allowed) {
      router.push(route('/investor/verify'));
      return;
    }
    setIntroBusy(true);
    try {
      await requestIntro(company.startupId);
    } finally {
      setIntroBusy(false);
    }
  }

  function openSchedule() {
    if (!gate.allowed) {
      router.push(route('/investor/verify'));
      return;
    }
    setScheduleOpen(true);
  }

  return (
    <Animated.View entering={FadeInDown.duration(250)} className="flex-1 bg-obsidian">
      <View
        className="flex-row items-center justify-between border-b border-graphite-soft px-[18px] pb-3"
        style={{ paddingTop: insets.top + 4 }}>
        <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={10}>
          <Txt className="text-[19px] text-bone">←</Txt>
        </Pressable>
        <Mono className="text-[10px] text-bone-faint" style={{ letterSpacing: 1.2 }}>
          DEEP DIVE
        </Mono>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={watched ? 'Remove from watchlist' : 'Add to watchlist'}
          onPress={() => toggleWatch(company.startupId)}
          hitSlop={10}>
          <Txt className="text-[17px]" style={{ color: watched ? C.flag : C.boneFaint }}>
            {watched ? '★' : '☆'}
          </Txt>
        </Pressable>
      </View>

      <ScrollView
        className="flex-1"
        contentContainerStyle={{ paddingHorizontal: 18, paddingTop: 18, paddingBottom: 14 }}
        showsVerticalScrollIndicator={false}>
        <View className="flex-row items-start gap-3">
          <View className="h-[44px] w-[44px] items-center justify-center rounded-[11px] border border-graphite-strong bg-carbon-high">
            <TxtSemi className="text-[14px]">{initials(name)}</TxtSemi>
          </View>
          <View className="min-w-0 flex-1">
            <TxtSemi className="text-[19px]" style={{ letterSpacing: -0.5 }}>
              {name}
            </TxtSemi>
            <Txt className="mt-[3px] text-[12.5px] text-bone-secondary" style={{ lineHeight: 18 }}>
              Summary card only. Figures arrive after SACI introduces you.
            </Txt>
          </View>
          <View className="items-end">
            <Mono className="text-[28px]" style={{ letterSpacing: -1.2, lineHeight: 30, color: scoreColor(fundScore ?? 0) }}>
              {fundScore ?? '—'}
            </Mono>
            <Txt className="mt-[2px] text-[8.5px] text-bone-faint" style={{ letterSpacing: 0.6 }}>
              FUNDABILITY
            </Txt>
          </View>
        </View>

        <View className="mt-3 flex-row flex-wrap gap-[7px]">
          <MetaPill label={company.stage ?? '—'} />
          <MetaPill label={company.country ?? '—'} />
          <MetaPill label={company.sector ?? '—'} />
        </View>

        <View className="mt-[14px] flex-row gap-[14px] border-b border-graphite-soft pb-[14px]">
          {['Website ↗', 'Product ↗', 'Deck ↓'].map((l) => (
            <Txt key={l} className="text-[11.5px] text-bone-secondary">
              {l}
            </Txt>
          ))}
        </View>

        {!verified ? (
          <Pressable
            accessibilityRole="button"
            onPress={() => router.push(route('/investor/verify'))}
            className="mt-4 rounded-[11px] p-[13px]"
            style={{ borderWidth: 1, borderColor: 'rgba(255,122,61,0.35)', backgroundColor: 'rgba(255,122,61,0.08)' }}>
            <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: C.flag }}>
              VERIFY TO CONTACT
            </Mono>
            <Txt className="mt-2 text-[12.5px] text-bone-secondary" style={{ lineHeight: 19 }}>
              Founders only take introductions and calls from verified investors. It takes a minute — four fields, no
              documents.
            </Txt>
            <TxtSemi className="mt-2 text-[12.5px]" style={{ color: C.flag }}>
              Verify your profile →
            </TxtSemi>
          </Pressable>
        ) : null}

        <View className="mt-4">
          <Segmented options={PANES} value={pane} onChange={setPane} grow size="md" />
        </View>

        {pane === 'metrics' ? (
          <View className="mt-4 gap-5">
            <View
              className="flex-row flex-wrap overflow-hidden rounded-[11px]"
              style={{ backgroundColor: C.carbonTop, borderWidth: 1, borderColor: C.carbonTop, gap: 1 }}>
              {[
                { k: 'FUNDABILITY', v: fundScore === null ? '—' : String(fundScore) },
                {
                  k: 'SALEABILITY',
                  v: company.saleability.score === null ? '—' : String(company.saleability.score),
                },
                { k: 'LEVEL', v: company.fundability.level },
                { k: 'RUBRIC', v: company.rubricVersion },
              ].map((m) => (
                <View key={m.k} className="bg-carbon-low px-[13px] py-3" style={{ width: '49.7%' }}>
                  <Txt className="text-[9.5px] text-bone-faint" style={{ letterSpacing: 0.5 }}>
                    {m.k}
                  </Txt>
                  <MonoMed className="mt-1 text-[15px]">{m.v}</MonoMed>
                </View>
              ))}
            </View>
            <Txt className="text-[12.5px] text-bone-muted" style={{ lineHeight: 19 }}>
              Revenue, runway, team and memos are full-report material. They reach you only after SACI
              approves an introduction and reveals a report.
            </Txt>
          </View>
        ) : (
          <View className="mt-4 gap-[18px]">
            <Txt className="text-[12.5px] text-bone-secondary" style={{ lineHeight: 21 }}>
              The AI analyst can discuss this summary card. It will not invent MRR, runway, or contact
              details.
            </Txt>
          </View>
        )}
      </ScrollView>

      <View className="border-t border-graphite-soft bg-obsidian px-[18px] pt-3" style={{ paddingBottom: insets.bottom + 14 }}>
        <Txt className="mb-[9px] text-center text-[11px] text-bone-faint">
          {callSent ? 'Call request sent — awaiting their answer' : 'SACI brokers the introduction'}
        </Txt>
        <View className="flex-row gap-2">
          <View style={{ width: 110 }}>
            <Button label={callSent ? 'Requested' : 'Schedule'} variant="secondary" height={46} disabled={callSent} onPress={openSchedule} />
          </View>
          <View className="flex-1">
            <Button
              label={introSent ? 'Introduction requested ✓' : 'Request direct introduction'}
              height={46}
              loading={introBusy}
              disabled={introSent}
              onPress={intro}
            />
          </View>
        </View>
      </View>

      <ScheduleCallSheet
        visible={scheduleOpen}
        onClose={() => setScheduleOpen(false)}
        companyName={name}
        onSubmit={async (input) => {
          await api.requestCall({ companyId: 0, ...input });
          setCallSent(true);
        }}
      />
    </Animated.View>
  );
}
