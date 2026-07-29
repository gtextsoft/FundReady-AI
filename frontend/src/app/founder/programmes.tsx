import { useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';

import { Button } from '@/components/ui/button';
import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { api } from '@/api';
import { useFounder } from '@/store/founder';

const PROGRAMMES = [
  {
    key: 'readiness' as const,
    badge: 'PRESCRIBED · 6 WEEKS',
    title: 'The Funding Readiness Challenge',
    body: 'For scores below the investor screening floor. Rebuilds the pitch narrative and forces clarity on unit economics before you burn warm intros.',
    bullets: [
      'Weekly teardown of your deck with an operating partner',
      'CAC/LTV instrumentation clinic',
      'Re-score at week 6, free of charge',
    ],
    accent: C.amb,
    border: '#3d2f14',
    gradient: ['rgba(245,166,35,0.14)', 'rgba(245,166,35,0.02)'] as [string, string],
    variant: 'amber' as const,
  },
  {
    key: 'wealth' as const,
    badge: 'UNLOCKED · 10 WEEKS',
    title: 'The Wealth Creation Challenge',
    body: 'For companies already clearing the floor. Compounding what works and building an investor pipeline you actually control.',
    bullets: [
      'Warm routing to matched VC and PE mandates',
      'Scaling playbooks for channel and pricing',
      'Live listing in the investor dealflow database',
    ],
    accent: C.grn,
    border: '#14351f',
    gradient: ['rgba(12,206,107,0.14)', 'rgba(12,206,107,0.02)'] as [string, string],
    variant: 'green' as const,
  },
];

export default function Programmes() {
  const insets = useSafeAreaInsets();
  const assessment = useFounder((s) => s.assessment);
  const [enrolled, setEnrolled] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const recommended = assessment?.route ?? null;

  async function enrol(key: 'readiness' | 'wealth') {
    setBusy(key);
    try {
      await api.enrol(key);
      setEnrolled((e) => [...e, key]);
    } finally {
      setBusy(null);
    }
  }

  return (
    <View className="flex-1 bg-ground">
      <View className="flex-row items-center justify-between px-[18px] pb-3" style={{ paddingTop: insets.top + 4 }}>
        <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={10}>
          <Txt className="text-[19px] text-ink">←</Txt>
        </Pressable>
        <Mono className="text-[10px] text-ink-faint" style={{ letterSpacing: 1.2 }}>
          PROGRAMMES
        </Mono>
        <View className="w-5" />
      </View>

      <ScrollView
        className="flex-1"
        contentContainerStyle={{ paddingHorizontal: 18, paddingBottom: insets.bottom + 24, gap: 12 }}
        showsVerticalScrollIndicator={false}>
        {PROGRAMMES.map((p) => {
          const isRecommended = recommended === p.key;
          const done = enrolled.includes(p.key);
          return (
            <View key={p.key} className="overflow-hidden rounded-[14px]" style={{ borderWidth: 1, borderColor: p.border }}>
              <LinearGradient colors={p.gradient} start={{ x: 0.1, y: 0 }} end={{ x: 0.9, y: 1 }} className="p-5">
                <View className="flex-row items-center gap-2">
                  <View className="rounded-[4px] px-[7px] py-[3px]" style={{ borderWidth: 1, borderColor: `${p.accent}59` }}>
                    <Mono className="text-[9.5px]" style={{ letterSpacing: 1.2, color: p.accent }}>
                      {p.badge}
                    </Mono>
                  </View>
                  {isRecommended ? (
                    <View className="rounded-[4px] bg-ink px-[7px] py-[3px]">
                      <Mono className="text-[9.5px] text-ground" style={{ letterSpacing: 1 }}>
                        RECOMMENDED
                      </Mono>
                    </View>
                  ) : null}
                </View>

                <TxtSemi className="mb-[6px] mt-[13px] text-[21px]" style={{ letterSpacing: -0.6 }}>
                  {p.title}
                </TxtSemi>
                <Txt className="mb-4 text-[13px] text-ink-muted" style={{ lineHeight: 20 }}>
                  {p.body}
                </Txt>

                <View className="mb-[18px] gap-[7px]">
                  {p.bullets.map((b) => (
                    <View key={b} className="flex-row gap-[9px]">
                      <Txt className="text-[12.5px]" style={{ color: p.accent }}>
                        →
                      </Txt>
                      <Txt className="flex-1 text-[12.5px] text-ink" style={{ lineHeight: 19 }}>
                        {b}
                      </Txt>
                    </View>
                  ))}
                </View>

                <Button
                  label={done ? 'Enrolled ✓' : `Enrol in ${p.key === 'readiness' ? 'Funding Readiness' : 'Wealth Creation'}`}
                  variant={p.variant}
                  loading={busy === p.key}
                  disabled={done}
                  onPress={() => enrol(p.key)}
                />
              </LinearGradient>
            </View>
          );
        })}
      </ScrollView>
    </View>
  );
}
