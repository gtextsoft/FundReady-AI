import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, TextInput, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { ScheduleCallSheet } from '@/components/investor/schedule-call-sheet';
import { Button } from '@/components/ui/button';
import { MetaPill } from '@/components/ui/controls';
import { Eyebrow, FieldLabel, Mono, Txt, TxtSemi } from '@/components/ui/text';
import { Font } from '@/theme/tokens';
import { useThemeColors } from '@/theme/use-theme-colors';
import { Unavailable } from '@/components/unavailable';
import { api } from '@/api';
import type { DiscoveredStartup } from '@/domain/discovery';
import {
  stageLabel,
  verdictColor,
  verdictLabel,
  verdictScoreText,
} from '@/domain/discovery-format';
import { investorGate } from '@/domain/access';
import { gateCopy } from '@/domain/gate-copy';
import type { Interest } from '@/domain/interest';
import { initials } from '@/lib/format';
import { route, VERIFY_EMAIL } from '@/lib/routes';
import { useInvestor } from '@/store/investor';
import { useSession } from '@/store/session';

/**
 * Summary-tier deep dive.
 *
 * No MRR, memos, or team — those arrive only after a FundReady AI reveal. Contact is
 * express-interest, not a direct intro/call to the founder.
 */
export default function CompanyDetail() {
  const insets = useSafeAreaInsets();
  const colors = useThemeColors();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [startup, setStartup] = useState<DiscoveredStartup | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [justSent, setJustSent] = useState(false);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [callError, setCallError] = useState<string | null>(null);

  const watchlist = useInvestor((s) => s.watchlist);
  const toggleWatch = useInvestor((s) => s.toggleWatch);
  const interestedIds = useInvestor((s) => s.interestedIds);
  const interests = useInvestor((s) => s.interests);
  const expressInterest = useInvestor((s) => s.expressInterest);
  const loadInterests = useInvestor((s) => s.loadInterests);

  const account = useSession((s) => s.investorAccount);
  const interestGate = account ? investorGate(account, 'expressInterest') : { allowed: false, reason: 'email' as const };
  const callGate = account ? investorGate(account, 'scheduleCall') : { allowed: false, reason: 'email' as const };

  useEffect(() => {
    void loadInterests();
  }, [loadInterests]);

  useEffect(() => {
    let live = true;
    api
      .getDiscoveredStartup(String(id))
      .then((c) => {
        if (!live) return;
        setStartup(c);
        setError(null);
      })
      .catch((e: unknown) => {
        if (!live) return;
        setStartup(null);
        setError(e);
      });
    return () => {
      live = false;
    };
  }, [id]);

  if (error) {
    return (
      <View className="flex-1 bg-ground px-[18px]" style={{ paddingTop: insets.top + 16 }}>
        <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={10}>
          <Txt className="mb-4 text-[19px] text-ink">←</Txt>
        </Pressable>
        <Unavailable
          title="This startup could not be loaded"
          error={error}
          onRetry={() => {
            setError(null);
            setStartup(null);
            api
              .getDiscoveredStartup(String(id))
              .then(setStartup)
              .catch(setError);
          }}
        />
      </View>
    );
  }

  if (!startup) {
    return (
      <View className="flex-1 items-center justify-center bg-ground">
        <ActivityIndicator color={colors.inkMuted} />
      </View>
    );
  }

  const name = startup.name?.trim() || 'Unnamed startup';
  const watched = watchlist.includes(startup.startupId);
  const already = interestedIds.includes(startup.startupId) || justSent;
  const interest: Interest | undefined = interests.find((i) => i.startupId === startup.startupId);
  const canSchedule =
    Boolean(interest) &&
    interest!.status !== 'declined' &&
    interest!.status !== 'withdrawn' &&
    callGate.allowed;
  const fundColor = verdictColor(startup.fundability.level);

  async function sendInterest() {
    if (!startup || already) return;
    if (!interestGate.allowed) {
      setSubmitError(
        interestGate.reason === 'email'
          ? 'Confirm your email address before expressing interest.'
          : 'Verify your identity before expressing interest.',
      );
      return;
    }
    setBusy(true);
    setSubmitError(null);
    try {
      await expressInterest(startup.startupId, note);
      setJustSent(true);
    } catch (e: unknown) {
      setSubmitError(e instanceof Error ? e.message : 'Could not send interest.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Animated.View entering={FadeInDown.duration(250)} className="flex-1 bg-ground">
      <View
        className="flex-row items-center justify-between border-b border-line-soft px-[18px] pb-3"
        style={{ paddingTop: insets.top + 4 }}>
        <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={10}>
          <Txt className="text-[19px] text-ink">←</Txt>
        </Pressable>
        <Mono className="text-[10px] text-ink-faint" style={{ letterSpacing: 1.2 }}>
          SUMMARY
        </Mono>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={watched ? 'Remove from watchlist' : 'Add to watchlist'}
          onPress={() => toggleWatch(startup.startupId)}
          hitSlop={10}>
          <Txt className="text-[17px]" style={{ color: watched ? colors.amb : colors.inkFaint }}>
            {watched ? '★' : '☆'}
          </Txt>
        </Pressable>
      </View>

      <ScrollView
        className="flex-1"
        contentContainerStyle={{ paddingHorizontal: 18, paddingTop: 18, paddingBottom: 14 }}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled">
        <View className="flex-row items-start gap-3">
          <View className="h-[44px] w-[44px] items-center justify-center rounded-[11px] border border-line-strong bg-surface-3">
            <TxtSemi className="text-[14px]">{initials(name)}</TxtSemi>
          </View>
          <View className="min-w-0 flex-1">
            <TxtSemi className="text-[19px]" style={{ letterSpacing: -0.5 }}>
              {name}
            </TxtSemi>
            <Txt className="mt-[3px] text-[12.5px] text-ink-muted">
              What you can see: summary scores and sector. What FundReady AI brokers next: introductions
              and any deeper report after review.
            </Txt>
          </View>
          <View className="items-end">
            <Mono className="text-[28px]" style={{ letterSpacing: -1.2, lineHeight: 30, color: fundColor }}>
              {verdictScoreText(startup.fundability)}
            </Mono>
            <Txt className="mt-[2px] text-[8.5px] text-ink-faint" style={{ letterSpacing: 0.6 }}>
              FUNDABILITY
            </Txt>
          </View>
        </View>

        <View className="mt-3 flex-row flex-wrap gap-[7px]">
          {startup.stage ? <MetaPill label={stageLabel(startup.stage)} /> : null}
          {startup.country ? <MetaPill label={startup.country} /> : null}
          {startup.sector ? <MetaPill label={startup.sector} /> : null}
        </View>

        <Eyebrow className="mb-[10px] mt-6">AUDIT VERDICTS</Eyebrow>
        <View className="gap-[9px]">
          <VerdictCard title="Fundability" verdict={startup.fundability} />
          <VerdictCard title="Saleability" verdict={startup.saleability} />
        </View>

        <Txt className="mt-4 text-[11px] text-ink-faint" style={{ lineHeight: 16 }}>
          Rubric {startup.rubricVersion}
          {startup.publishedAt
            ? ` · Published ${new Date(startup.publishedAt).toLocaleDateString()}`
            : ''}
        </Txt>

        <Eyebrow className="mb-[10px] mt-6">AI ANALYST</Eyebrow>
        <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
          <Txt className="mb-3 text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
            Ask about this summary card. Answers stay on the summary tier — full report fields are never loaded.
          </Txt>
          <Button
            label="Open AI analyst"
            height={40}
            variant="secondary"
            onPress={() => router.push(route(`/investor/company/${startup.startupId}/analyst`))}
          />
        </View>

        {interest && interest.revealedRunIds.length > 0 ? (
          <>
            <Eyebrow className="mb-[10px] mt-6">REVEALED REPORTS</Eyebrow>
            <View className="gap-[9px]">
              {interest.revealedRunIds.map((runId) => (
                <View key={runId} className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
                  <TxtSemi className="text-[13px]">Full report available</TxtSemi>
                  <Mono className="mt-1 text-[10px] text-ink-faint">{runId.slice(0, 8)}…</Mono>
                  <View className="mt-3">
                    <Button
                      label="Open revealed report"
                      height={40}
                      onPress={() =>
                        router.push(route(`/investor/report/${interest.id}/${runId}`))
                      }
                    />
                  </View>
                </View>
              ))}
            </View>
          </>
        ) : null}

        <Eyebrow className="mb-[10px] mt-6">EXPRESS INTEREST</Eyebrow>
        <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
          {already ? (
            <View className="gap-2">
              <TxtSemi className="text-[14px]" style={{ color: colors.grn }}>
                Interest received
              </TxtSemi>
              <Txt className="text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
                FundReady AI reviews introductions before anyone is connected. Track status on your
                Profile.
              </Txt>
              {canSchedule ? (
                <>
                  <Button label="Propose a call" height={40} onPress={() => setScheduleOpen(true)} />
                  {callError ? (
                    <Txt className="text-[12px]" style={{ color: colors.red }}>
                      {callError}
                    </Txt>
                  ) : null}
                </>
              ) : interest && !callGate.allowed ? (
                <Txt className="text-[12px] text-ink-muted" style={{ lineHeight: 18 }}>
                  {gateCopy(callGate.reason, 'investor').body}
                </Txt>
              ) : null}
              <Button
                label="View my interests"
                height={40}
                variant="secondary"
                onPress={() => router.push(route('/investor/profile'))}
              />
            </View>
          ) : (
            <>
              <Txt className="mb-3 text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
                FundReady AI brokers every introduction. Your note is for FundReady AI only — the founder
                never sees it.
              </Txt>
              <View className="gap-[7px]">
                <FieldLabel>Note for FundReady AI (optional)</FieldLabel>
                <TextInput
                  className="min-h-[72px] rounded-[9px] border border-line bg-ground px-3 py-2 text-[13px] text-ink"
                  placeholder="Thesis fit, cheque size, geography…"
                  placeholderTextColor={colors.inkFaint}
                  multiline
                  value={note}
                  onChangeText={setNote}
                  style={{ fontFamily: Font.regular, textAlignVertical: 'top' }}
                />
              </View>
              {!interestGate.allowed ? (
                <Txt className="mt-2 text-[12px]" style={{ color: colors.amb }}>
                  {gateCopy(interestGate.reason, 'investor').body}
                </Txt>
              ) : null}
              {submitError ? (
                <Txt className="mt-2 text-[12px]" style={{ color: colors.red }}>
                  {submitError}
                </Txt>
              ) : null}
            </>
          )}
        </View>
      </ScrollView>

      <View className="border-t border-line-soft bg-ground px-[18px] pt-3" style={{ paddingBottom: insets.bottom + 14 }}>
        {already ? (
          <Button label="Interest registered ✓" height={46} disabled />
        ) : !interestGate.allowed ? (
          <Button
            label={gateCopy(interestGate.reason, 'investor').cta}
            height={46}
            onPress={() =>
              router.push(
                interestGate.reason === 'email' ? VERIFY_EMAIL : route('/investor/verify'),
              )
            }
          />
        ) : (
          <Button label="Express interest" height={46} loading={busy} onPress={sendInterest} />
        )}
      </View>

      {interest ? (
        <ScheduleCallSheet
          visible={scheduleOpen}
          onClose={() => setScheduleOpen(false)}
          companyName={name}
          onSubmit={async ({ proposedAt, note: message }) => {
            setCallError(null);
            try {
              await api.requestCall({
                interestId: interest.id,
                proposedAt,
                message,
              });
            } catch (e) {
              setCallError(e instanceof Error ? e.message : 'Could not send call request.');
              throw e;
            }
          }}
        />
      ) : null}
    </Animated.View>
  );
}

function VerdictCard({
  title,
  verdict,
}: {
  title: string;
  verdict: DiscoveredStartup['fundability'];
}) {
  const color = verdictColor(verdict.level);
  return (
    <View className="rounded-[11px] border border-line bg-surface-1 px-[13px] py-3">
      <View className="flex-row items-center justify-between">
        <TxtSemi className="text-[13px]">{title}</TxtSemi>
        <Mono className="text-[16px]" style={{ color }}>
          {verdictScoreText(verdict)}
        </Mono>
      </View>
      <Txt className="mt-1 text-[12px] capitalize text-ink-muted">{verdictLabel(verdict.level)}</Txt>
    </View>
  );
}
