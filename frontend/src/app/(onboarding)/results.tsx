import { useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';

import { Button } from '@/components/ui/button';
import { ScoreRing } from '@/components/ui/score-ring';
import { Eyebrow, Mono, Txt, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { Unavailable } from '@/components/unavailable';
import { api } from '@/api';
import type { Assessment, Insight } from '@/domain/types';
import { FOUNDER_HOME } from '@/lib/routes';
import { useFounder } from '@/store/founder';

export default function Results() {
  const insets = useSafeAreaInsets();
  const profile = useFounder((s) => s.profile);
  const stored = useFounder((s) => s.assessment);
  const liveAssessment = useFounder((s) => s.liveAssessment);

  // `stored` is the audit the server returned. There is no audit engine yet
  // (Phase 2), so in practice this is always the local estimate — which is a
  // heuristic over the form, not a scored audit, and is labelled as such below.
  const a: Assessment = stored ?? liveAssessment();
  const provisional = stored === null;

  const [openStrengths, setOpenStrengths] = useState(true);
  const [openRisks, setOpenRisks] = useState(true);

  return (
    <ScrollView
      className="flex-1 bg-ground"
      contentContainerStyle={{ paddingTop: insets.top + 8, paddingHorizontal: 20, paddingBottom: insets.bottom + 34 }}
      showsVerticalScrollIndicator={false}>
      <View className="mb-[22px] flex-row items-center justify-between">
        <View>
          <Txt className="text-[12px] text-ink-dim">Assessment complete</Txt>
          <TxtSemi className="text-[19px]" style={{ letterSpacing: -0.5 }}>
            {profile.company || 'Your company'}
          </TxtSemi>
        </View>
        <View className="rounded-[5px] border border-line-strong px-2 py-1">
          <Mono className="text-[10px] text-ink-muted">{profile.sector || 'Unclassified'}</Mono>
        </View>
      </View>

      {provisional ? (
        <View
          className="mb-4 rounded-[12px] p-[13px]"
          style={{ borderWidth: 1, borderStyle: 'dashed', borderColor: C.lineDash }}>
          <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: C.amb }}>
            PROVISIONAL ESTIMATE
          </Mono>
          <Txt className="mt-[7px] text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
            Calculated on this device from what you entered. It is not a SACI audit — nothing here has been
            verified against documents, and no investor can see it. The real scored audit arrives when the
            audit engine is built.
          </Txt>
        </View>
      ) : null}

      <View className="overflow-hidden rounded-[14px] border border-line">
        <LinearGradient colors={['#0f0f0f', '#0a0a0a']} className="items-center px-5 pb-[22px] pt-[26px]">
          <ScoreRing score={a.score} color={a.bandColor} />
          <TxtSemi className="mt-[14px] text-[14px]" style={{ color: a.bandColor }}>
            {a.bandLabel}
          </TxtSemi>
          <View className="mt-[14px] w-full flex-row gap-2">
            <FitTile label="VC-FIT" value={a.vcFit} />
            <FitTile label="PE-FIT" value={a.peFit} />
          </View>
        </LinearGradient>
      </View>

      <Section
        title="Key strengths"
        dotColor={C.grn}
        open={openStrengths}
        onToggle={() => setOpenStrengths((v) => !v)}
        items={a.strengths}
        className="mt-6"
      />
      <Section
        title="Critical gaps"
        dotColor={C.amb}
        open={openRisks}
        onToggle={() => setOpenRisks((v) => !v)}
        items={a.risks}
        className="mt-[22px]"
      />

      <Eyebrow className="mb-[10px] mt-7">YOUR RECOMMENDED PATH</Eyebrow>

      {a.route === 'readiness' ? (
        <ProgrammeCard
          badge="PRESCRIBED · 6 WEEKS"
          title="The Funding Readiness Challenge"
          body="Your score sits below the investor screening floor. This programme rebuilds your pitch narrative and forces clarity on unit economics before you burn warm intros."
          bullets={[
            'Weekly teardown of your deck with an operating partner',
            'CAC/LTV instrumentation clinic',
            'Re-score at week 6, free of charge',
          ]}
          accent={C.amb}
          borderColor="#3d2f14"
          gradient={['rgba(245,166,35,0.14)', 'rgba(245,166,35,0.02)']}
          cta="Enrol in Funding Readiness"
          variant="amber"
          programme="readiness"
        />
      ) : (
        <ProgrammeCard
          badge="UNLOCKED · 10 WEEKS"
          title="The Wealth Creation Challenge"
          body="You clear the screening floor. This track is about compounding what already works and building an investor pipeline you actually control."
          bullets={[
            'Warm routing to matched VC and PE mandates',
            'Scaling playbooks for channel and pricing',
            'Live listing in the investor dealflow database',
          ]}
          accent={C.grn}
          borderColor="#14351f"
          gradient={['rgba(12,206,107,0.14)', 'rgba(12,206,107,0.02)']}
          cta="Enrol in Wealth Creation"
          variant="green"
          programme="wealth"
        />
      )}

      <View className="mt-[10px]">
        <Button label="Go to your dashboard →" variant="secondary" onPress={() => router.replace(FOUNDER_HOME)} />
      </View>

      <Txt className="mt-[18px] text-center text-[11px] text-ink-faint" style={{ lineHeight: 17 }}>
        Re-run your assessment any time your metrics change. Investors see your latest score only.
      </Txt>
    </ScrollView>
  );
}

function FitTile({ label, value }: { label: string; value: string }) {
  return (
    <View className="flex-1 items-center rounded-[9px] border border-line p-[10px]">
      <Txt className="text-[10px] text-ink-faint" style={{ letterSpacing: 0.6 }}>
        {label}
      </Txt>
      <TxtSemi className="mt-[3px] text-[14px]">{value}</TxtSemi>
    </View>
  );
}

function Section({
  title,
  dotColor,
  open,
  onToggle,
  items,
  className,
}: {
  title: string;
  dotColor: string;
  open: boolean;
  onToggle: () => void;
  items: Insight[];
  className?: string;
}) {
  return (
    <View className={className}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        onPress={onToggle}
        className="w-full flex-row items-center justify-between pb-3">
        <View className="flex-row items-center gap-[9px]">
          <View className="h-[6px] w-[6px] rounded-full" style={{ backgroundColor: dotColor }} />
          <TxtSemi className="text-[14px]">{title}</TxtSemi>
        </View>
        <Txt className="text-[12px] text-ink-faint">{open ? 'Hide' : 'Show'}</Txt>
      </Pressable>

      {open ? (
        <View className="gap-2">
          {items.map((it) => (
            <View key={it.title} className="rounded-[10px] border border-line bg-surface-1 p-[14px]">
              <TxtSemi className="mb-[5px] text-[13.5px]">{it.title}</TxtSemi>
              <Txt className="text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
                {it.body}
              </Txt>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

function ProgrammeCard({
  badge,
  title,
  body,
  bullets,
  accent,
  borderColor,
  gradient,
  cta,
  variant,
  programme,
}: {
  badge: string;
  title: string;
  body: string;
  bullets: string[];
  accent: string;
  borderColor: string;
  gradient: [string, string];
  cta: string;
  variant: 'amber' | 'green';
  programme: 'readiness' | 'wealth';
}) {
  const [enrolled, setEnrolled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function enrol() {
    setBusy(true);
    setError(null);
    try {
      await api.enrol(programme);
      setEnrolled(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <View className="overflow-hidden rounded-[14px]" style={{ borderWidth: 1, borderColor }}>
      <LinearGradient colors={gradient} start={{ x: 0.1, y: 0 }} end={{ x: 0.9, y: 1 }} className="p-5">
        <View className="self-start rounded-[4px] px-[7px] py-[3px]" style={{ borderWidth: 1, borderColor: `${accent}59` }}>
          <Mono className="text-[9.5px]" style={{ letterSpacing: 1.2, color: accent }}>
            {badge}
          </Mono>
        </View>

        <TxtSemi className="mb-[6px] mt-[13px] text-[21px]" style={{ letterSpacing: -0.6 }}>
          {title}
        </TxtSemi>
        <Txt className="mb-4 text-[13px] text-ink-muted" style={{ lineHeight: 20 }}>
          {body}
        </Txt>

        <View className="mb-[18px] gap-[7px]">
          {bullets.map((b) => (
            <View key={b} className="flex-row gap-[9px]">
              <Txt className="text-[12.5px]" style={{ color: accent }}>
                →
              </Txt>
              <Txt className="flex-1 text-[12.5px] text-ink" style={{ lineHeight: 19 }}>
                {b}
              </Txt>
            </View>
          ))}
        </View>

        <Button label={enrolled ? 'Enrolled ✓' : cta} variant={variant} loading={busy} disabled={enrolled} onPress={enrol} />

        {error ? <Unavailable title="Enrolment is not live" error={error} className="mt-3" /> : null}
      </LinearGradient>
    </View>
  );
}
