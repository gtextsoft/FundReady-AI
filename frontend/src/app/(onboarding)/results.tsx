import { useEffect, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';

import { Button } from '@/components/ui/button';
import { ScoreRing } from '@/components/ui/score-ring';
import { Eyebrow, Mono, Txt, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { Unavailable } from '@/components/unavailable';
import { AuditFailed, AuditPending, AuditReportView } from '@/components/founder/audit-report';
import { api } from '@/api';
import type { Assessment, Insight } from '@/domain/types';
import { FOUNDER_HOME, VERIFY_EMAIL } from '@/lib/routes';
import { useBackTo } from '@/lib/use-back-to';
import { useFounder } from '@/store/founder';
import { useSession } from '@/store/session';

export default function Results() {
  const insets = useSafeAreaInsets();
  const profile = useFounder((s) => s.profile);
  const stored = useFounder((s) => s.assessment);
  const liveAssessment = useFounder((s) => s.liveAssessment);

  const run = useFounder((s) => s.run);
  const report = useFounder((s) => s.report);
  const auditError = useFounder((s) => s.auditError);
  const resumeAudit = useFounder((s) => s.resumeAudit);

  // Same rule as the assessment screen: the submission is done, so back goes
  // forward to the dashboard rather than into the form.
  useBackTo(FOUNDER_HOME);

  // An audit outlives the screen that started it, so pick the newest one back
  // up on arrival. Skipped when this screen already has a run in hand.
  useEffect(() => {
    if (!run) void resumeAudit();
  }, [run, resumeAudit]);

  // `stored` is the prototype's on-device heuristic. The real audit is `report`
  // and it wins whenever it exists — the estimate is a stand-in for the wait,
  // not a second opinion.
  const a: Assessment = stored ?? liveAssessment();
  const provisional = report === null;

  const unmapped = useFounder((s) => s.unmapped);

  // Read off the account rather than pattern-matched out of the error text.
  // The server sends this as a plain `forbidden` with no distinct code, so the
  // message is the only other signal and matching on prose would break the
  // first time it is reworded.
  const founderAccount = useSession((s) => s.founderAccount);
  const needsEmail = founderAccount !== null && !founderAccount.emailVerified;

  const [openStrengths, setOpenStrengths] = useState(true);
  const [openRisks, setOpenRisks] = useState(true);

  return (
    <ScrollView
      className="flex-1 bg-obsidian"
      contentContainerStyle={{ paddingTop: insets.top + 8, paddingHorizontal: 20, paddingBottom: insets.bottom + 34 }}
      showsVerticalScrollIndicator={false}>
      <View className="mb-[22px] flex-row items-center justify-between">
        <View>
          <Txt className="text-[12px] text-bone-muted">Assessment complete</Txt>
          <TxtSemi className="text-[19px]" style={{ letterSpacing: -0.5 }}>
            {profile.company || 'Your company'}
          </TxtSemi>
        </View>
        <View className="rounded-[5px] border border-graphite-strong px-2 py-1">
          <Mono className="text-[10px] text-bone-secondary">{profile.sector || 'Unclassified'}</Mono>
        </View>
      </View>

      {/* The audit's own state comes first — while it is running, the estimate
          below is a stand-in for the wait, not a second opinion. */}
      {run && !report && run.status !== 'failed' ? <AuditPending run={run} /> : null}
      {run?.status === 'failed' ? <AuditFailed run={run} /> : null}
      {/* Everything past registration is gated on a confirmed address — the
          server answers every audit, profile and discovery route with 403
          "Verify your email address to continue" until then. That is the
          normal state for someone who just signed up, so it gets an
          instruction and a way out, not a raw error panel. */}
      {auditError && !run && needsEmail ? (
        <View
          className="mb-4 rounded-[12px] p-[13px]"
          style={{ borderWidth: 1, borderColor: '#4A2A16', backgroundColor: 'rgba(255,122,61,0.08)' }}>
          <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: C.flag }}>
            CONFIRM YOUR EMAIL
          </Mono>
          <Txt className="mb-3 mt-[7px] text-[12.5px] text-bone-secondary" style={{ lineHeight: 19 }}>
            Your answers are saved, but nothing can be audited until you confirm your address. Open
            the link we emailed you, then come back and run it again.
          </Txt>
          <Button
            label="Confirm my email"
            variant="flag"
            onPress={() => router.push(VERIFY_EMAIL)}
          />
        </View>
      ) : null}

      {auditError && !run && !needsEmail ? (
        <Unavailable title="The audit could not be started" error={auditError} className="mb-4" />
      ) : null}

      {provisional ? (
        <View
          className="mb-4 rounded-[12px] p-[13px]"
          style={{ borderWidth: 1, borderStyle: 'dashed', borderColor: C.graphiteBright }}>
          <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: C.flag }}>
            PROVISIONAL ESTIMATE
          </Mono>
          <Txt className="mt-[7px] text-[12.5px] text-bone-secondary" style={{ lineHeight: 19 }}>
            Calculated on this device from what you entered. It is not a FundReady audit — nothing here
            has been verified against your documents, and no investor can see it.
          </Txt>
        </View>
      ) : null}

      {/* Answers the server has no field for. Saying nothing here would let
          the screen imply everything typed was stored — and the audit would
          later be silent about figures the founder knows they entered. */}
      {unmapped.length > 0 ? (
        <View
          className="mb-4 rounded-[12px] p-[13px]"
          style={{ borderWidth: 1, borderStyle: 'dashed', borderColor: C.graphiteBright }}>
          <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: C.flag }}>
            NOT SAVED YET
          </Mono>
          <Txt className="mt-[7px] text-[12.5px] text-bone-secondary" style={{ lineHeight: 19 }}>
            {unmapped.length === 1 ? 'One answer has' : `${unmapped.length} answers have`} nowhere to
            be stored yet, so {unmapped.length === 1 ? 'it is' : 'they are'} not part of any audit:
          </Txt>
          {unmapped.map((answer) => (
            <Txt
              key={answer.field}
              className="mt-[6px] text-[12px] text-bone-faint"
              style={{ lineHeight: 18 }}>
              • {answer.field} — {answer.reason}
            </Txt>
          ))}
        </View>
      ) : null}

      {/* The real audit replaces the estimate rather than sitting beside it.
          Two scores on one screen, one of which is not the audit, is exactly
          the ambiguity the provisional label exists to prevent. */}
      {report ? (
        <AuditReportView report={report} />
      ) : (
        <>
          <View className="overflow-hidden rounded-[14px] border border-graphite">
            <LinearGradient
              colors={['#14181A', '#101415']}
              className="items-center px-5 pb-[22px] pt-[26px]">
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
            dotColor={C.signal}
            open={openStrengths}
            onToggle={() => setOpenStrengths((v) => !v)}
            items={a.strengths}
            className="mt-6"
          />
          <Section
            title="Critical gaps"
            dotColor={C.flag}
            open={openRisks}
            onToggle={() => setOpenRisks((v) => !v)}
            items={a.risks}
            className="mt-[22px]"
          />
        </>
      )}

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
          accent={C.flag}
          borderColor="#3d2f14"
          gradient={['rgba(255,122,61,0.14)', 'rgba(255,122,61,0.02)']}
          cta="Enrol in Funding Readiness"
          variant="flag"
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
          accent={C.signal}
          borderColor="#14351f"
          gradient={['rgba(198,242,78,0.14)', 'rgba(198,242,78,0.02)']}
          cta="Enrol in Wealth Creation"
          variant="primary"
          programme="wealth"
        />
      )}

      <View className="mt-[10px]">
        <Button label="Go to your dashboard →" variant="secondary" onPress={() => router.replace(FOUNDER_HOME)} />
      </View>

      <Txt className="mt-[18px] text-center text-[11px] text-bone-faint" style={{ lineHeight: 17 }}>
        Re-run your assessment any time your metrics change. Investors see your latest score only.
      </Txt>
    </ScrollView>
  );
}

function FitTile({ label, value }: { label: string; value: string }) {
  return (
    <View className="flex-1 items-center rounded-[9px] border border-graphite p-[10px]">
      <Txt className="text-[10px] text-bone-faint" style={{ letterSpacing: 0.6 }}>
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
        <Txt className="text-[12px] text-bone-faint">{open ? 'Hide' : 'Show'}</Txt>
      </Pressable>

      {open ? (
        <View className="gap-2">
          {items.map((it) => (
            <View key={it.title} className="rounded-[10px] border border-graphite bg-carbon-low p-[14px]">
              <TxtSemi className="mb-[5px] text-[13.5px]">{it.title}</TxtSemi>
              <Txt className="text-[12.5px] text-bone-secondary" style={{ lineHeight: 19 }}>
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
  variant: 'flag' | 'primary';
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
        <Txt className="mb-4 text-[13px] text-bone-secondary" style={{ lineHeight: 20 }}>
          {body}
        </Txt>

        <View className="mb-[18px] gap-[7px]">
          {bullets.map((b) => (
            <View key={b} className="flex-row gap-[9px]">
              <Txt className="text-[12.5px]" style={{ color: accent }}>
                →
              </Txt>
              <Txt className="flex-1 text-[12.5px] text-bone" style={{ lineHeight: 19 }}>
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
