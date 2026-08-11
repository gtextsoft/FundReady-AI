import { useEffect, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { ScheduleCallSheet } from '@/components/investor/schedule-call-sheet';
import { Button } from '@/components/ui/button';
import { Divider, MetaPill, Segmented } from '@/components/ui/controls';
import { Eyebrow, Mono, MonoMed, Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { C, scoreColor } from '@/theme/tokens';
import { Unavailable } from '@/components/unavailable';
import { api } from '@/api';
import { investorGate } from '@/domain/access';
import type { Company } from '@/domain/types';
import { arrLabel, growthColor, initials, TREND_MONTHS } from '@/lib/format';
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
  const [company, setCompany] = useState<Company | null>(null);
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
      .getCompany(Number(id))
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

  const watched = watchlist.includes(company.id);
  const introSent = introRequested.includes(company.id);
  const peak = Math.max(...company.trend);

  const metrics = [
    { k: 'MRR', v: `$${(company.mrr / 1000).toFixed(0)}k`, c: C.bone },
    { k: 'ARR RUN-RATE', v: arrLabel(company.mrr), c: C.bone },
    { k: 'MoM GROWTH', v: `+${company.growth}%`, c: growthColor(company.growth) },
    { k: 'GROSS MARGIN', v: `${company.margin}%`, c: company.margin >= 70 ? C.signal : C.flag },
    { k: 'LTV : CAC', v: `${company.ltvcac.toFixed(1)}:1`, c: company.ltvcac >= 3 ? C.signal : C.flag },
    { k: 'RUNWAY', v: `${company.runway} mo`, c: company.runway >= 12 ? C.bone : C.flag },
  ];

  async function intro() {
    if (!company || introSent) return;
    if (!gate.allowed) {
      router.push(route('/investor/verify'));
      return;
    }
    setIntroBusy(true);
    try {
      await requestIntro(company.id);
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
          onPress={() => toggleWatch(company.id)}
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
            <TxtSemi className="text-[14px]">{initials(company.name)}</TxtSemi>
          </View>
          <View className="min-w-0 flex-1">
            <TxtSemi className="text-[19px]" style={{ letterSpacing: -0.5 }}>
              {company.name}
            </TxtSemi>
            <Txt className="mt-[3px] text-[12.5px] text-bone-secondary" style={{ lineHeight: 18 }}>
              {company.tagline}
            </Txt>
          </View>
          <View className="items-end">
            <Mono className="text-[28px]" style={{ letterSpacing: -1.2, lineHeight: 30, color: scoreColor(company.score) }}>
              {company.score}
            </Mono>
            <Txt className="mt-[2px] text-[8.5px] text-bone-faint" style={{ letterSpacing: 0.6 }}>
              FUNDABILITY
            </Txt>
          </View>
        </View>

        <View className="mt-3 flex-row flex-wrap gap-[7px]">
          <MetaPill label={company.stage} />
          <MetaPill label={company.location} />
          <MetaPill label={company.sector} />
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
              {metrics.map((m) => (
                <View key={m.k} className="bg-carbon-low px-[13px] py-3" style={{ width: '49.7%' }}>
                  <Txt className="text-[9.5px] text-bone-faint" style={{ letterSpacing: 0.5 }}>
                    {m.k}
                  </Txt>
                  <MonoMed className="mt-1 text-[15px]" style={{ color: m.c }}>
                    {m.v}
                  </MonoMed>
                </View>
              ))}
            </View>

            <View>
              <Eyebrow className="mb-[10px] text-[9.5px]" style={{ letterSpacing: 1.2 }}>
                TRACTION — LAST 6 MONTHS
              </Eyebrow>
              <View className="h-[92px] flex-row items-end gap-[7px] rounded-[11px] border border-graphite bg-carbon-low p-[13px]">
                {company.trend.map((v, i) => (
                  <View key={i} className="h-full flex-1 items-center justify-end gap-[6px]">
                    <View className="w-full rounded-t-[3px] bg-bone" style={{ height: `${Math.max(4, (v / peak) * 100)}%` }} />
                    <Mono className="text-[9px] text-bone-faint">{TREND_MONTHS[i]}</Mono>
                  </View>
                ))}
              </View>
            </View>

            <View>
              <Eyebrow className="mb-[10px] text-[9.5px]" style={{ letterSpacing: 1.2 }}>
                TEAM
              </Eyebrow>
              <View
                className="overflow-hidden rounded-[11px]"
                style={{ backgroundColor: C.carbonTop, borderWidth: 1, borderColor: C.carbonTop, gap: 1 }}>
                {company.team.map((p) => (
                  <View key={p.name} className="flex-row items-center gap-[11px] bg-carbon-low px-[13px] py-[11px]">
                    <View className="h-[29px] w-[29px] items-center justify-center rounded-full border border-graphite-strong bg-carbon-top">
                      <Txt className="text-[10px] text-bone-secondary">{initials(p.name)}</Txt>
                    </View>
                    <View className="min-w-0 flex-1">
                      <TxtMed className="text-[12.5px]">{p.name}</TxtMed>
                      <Txt className="text-[11px] text-bone-muted">{p.role}</Txt>
                    </View>
                    <Txt className="text-[10.5px] text-bone-faint">{p.note}</Txt>
                  </View>
                ))}
              </View>
            </View>

            <View>
              <Eyebrow className="mb-[10px] text-[9.5px]" style={{ letterSpacing: 1.2 }}>
                UPLOADED ASSETS
              </Eyebrow>
              <View className="flex-row gap-[9px]">
                {[
                  { kind: 'PDF', label: 'Pitch deck' },
                  { kind: 'XLSX', label: 'Model' },
                ].map((a) => (
                  <View
                    key={a.kind}
                    className="flex-1 items-center justify-center gap-1 rounded-[10px] border border-graphite bg-carbon-low"
                    style={{ aspectRatio: 16 / 10 }}>
                    <Mono className="text-[9px] text-bone-faint">{a.kind}</Mono>
                    <Txt className="text-[11px] text-bone-secondary">{a.label}</Txt>
                  </View>
                ))}
              </View>
            </View>
          </View>
        ) : (
          <View className="mt-4 gap-[18px]">
            <View className="flex-row items-center gap-2">
              <View className="h-[5px] w-[5px] rounded-full" style={{ backgroundColor: C.signal }} />
              <Mono className="text-[9.5px] text-bone-secondary" style={{ letterSpacing: 1.2 }}>
                GENERATED {company.memoDate}
              </Mono>
            </View>

            <View>
              <TxtSemi className="mb-[7px] text-[13px]">Executive summary &amp; thesis</TxtSemi>
              <Txt className="text-[12.5px] text-bone-secondary" style={{ lineHeight: 21 }}>
                {company.memo1}
              </Txt>
            </View>

            <Divider />

            <View>
              <TxtSemi className="mb-[7px] text-[13px]">Why it fits a {company.match} mandate</TxtSemi>
              <Txt className="mb-[10px] text-[12.5px] text-bone-secondary" style={{ lineHeight: 21 }}>
                {company.memo2}
              </Txt>
              <View className="gap-[6px]">
                {company.fits.map((f) => (
                  <View key={f} className="flex-row gap-[9px]">
                    <Txt className="text-[12.5px]" style={{ color: C.signal }}>
                      ✓
                    </Txt>
                    <Txt className="flex-1 text-[12.5px]" style={{ lineHeight: 19 }}>
                      {f}
                    </Txt>
                  </View>
                ))}
              </View>
            </View>

            <Divider />

            <View>
              <TxtSemi className="mb-2 text-[13px]">Bottlenecks &amp; risk flags</TxtSemi>
              <View className="gap-2">
                {company.flags.map((f) => (
                  <View key={f.title} className="flex-row gap-[10px] rounded-[10px] border border-graphite bg-carbon-low px-3 py-[11px]">
                    <Txt className="mt-[2px] text-[10px]" style={{ color: f.color }}>
                      ●
                    </Txt>
                    <View className="flex-1">
                      <TxtMed className="mb-[3px] text-[12.5px]">{f.title}</TxtMed>
                      <Txt className="text-[12px] text-bone-secondary" style={{ lineHeight: 19 }}>
                        {f.body}
                      </Txt>
                    </View>
                  </View>
                ))}
              </View>
            </View>

            <Txt className="text-[10.5px] text-bone-ghost" style={{ lineHeight: 16 }}>
              Model-generated from founder-declared metrics. Not investment advice.
            </Txt>
          </View>
        )}
      </ScrollView>

      <View className="border-t border-graphite-soft bg-obsidian px-[18px] pt-3" style={{ paddingBottom: insets.bottom + 14 }}>
        <Txt className="mb-[9px] text-center text-[11px] text-bone-faint">
          {callSent ? 'Call request sent — awaiting their answer' : `Founder responds in ~${company.responseTime} on average`}
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
        companyName={company.name}
        onSubmit={async (input) => {
          await api.requestCall({ companyId: company.id, ...input });
          setCallSent(true);
        }}
      />
    </Animated.View>
  );
}
