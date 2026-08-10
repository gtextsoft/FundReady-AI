import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ModuleTile } from '@/components/founder/module-tile';
import { NextActionCard } from '@/components/founder/next-action';
import { PublishStrip } from '@/components/founder/publish-strip';
import { StatusBanner } from '@/components/founder/status-banner';
import { Button } from '@/components/ui/button';
import { Mark } from '@/components/ui/mark';
import { Eyebrow, Mono, Txt, TxtSemi } from '@/components/ui/text';
import { C, band } from '@/theme/tokens';
import { useThemeColors } from '@/theme/use-theme-colors';
import { api } from '@/api';
import { gate, hasAccess, isPaid, type Gate } from '@/domain/access';
import type { AuditReport, AuditRun } from '@/domain/audit';
import type { ReadinessSummary } from '@/domain/readiness';
import { assess } from '@/domain/scoring';
import type { FounderAccount } from '@/domain/types';
import { route, VERIFY_EMAIL } from '@/lib/routes';
import { isAssessmentComplete, useFounder } from '@/store/founder';
import { useNotifications } from '@/store/notifications';
import { useSession } from '@/store/session';

const ALLOWED: Gate = { allowed: true, reason: null };

/** Home. Everything the founder can reach, with locks shown rather than hidden. */
export default function FounderDashboard() {
  const insets = useSafeAreaInsets();
  const colors = useThemeColors();

  const session = useSession((s) => s.session);
  const account = useSession((s) => s.founderAccount);
  const refreshAccount = useSession((s) => s.refreshAccount);

  const profile = useFounder((s) => s.profile);
  const report = useFounder((s) => s.report);
  const run = useFounder((s) => s.run);
  const missingFields = useFounder((s) => s.missingFields);
  const loadProfile = useFounder((s) => s.load);
  const loadLatestAudit = useFounder((s) => s.loadLatestAudit);

  const loadNotifications = useNotifications((s) => s.load);
  const unread = useNotifications((s) => s.unreadCount());
  const pendingCalls = useNotifications((s) => s.pendingCalls().length);

  const [summary, setSummary] = useState<ReadinessSummary | null>(null);
  const [visible, setVisible] = useState(false);
  const [publishBusy, setPublishBusy] = useState(false);
  const [publishError, setPublishError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const refreshHome = useCallback(async () => {
    setRefreshing(true);
    try {
      await Promise.all([refreshAccount(), loadProfile(), loadLatestAudit()]);
      loadNotifications('founder');
      try {
        const [sum, vis] = await Promise.all([api.getTasksSummary(), api.getVisibility()]);
        setSummary(sum);
        setVisible(vis.investorVisible);
      } catch {
        // No profile / email gate — leave widgets empty.
      }
    } finally {
      setRefreshing(false);
    }
  }, [refreshAccount, loadNotifications, loadProfile, loadLatestAudit]);

  useFocusEffect(
    useCallback(() => {
      void refreshHome();
    }, [refreshHome]),
  );

  // Resume incomplete intake: if email is confirmed but assessment never ran,
  // send them back into onboarding rather than leaving them on an empty Home.
  useFocusEffect(
    useCallback(() => {
      if (!account?.emailVerified) return;
      if (report || run) return;
      if (isAssessmentComplete(profile)) return;
      // Only auto-route when the profile is still essentially empty — a
      // half-finished form should resume via the Next action / Assessment tile.
      if (profile.company.trim() || profile.sector) return;
      router.replace(route('/onboarding'));
    }, [account?.emailVerified, report, run, profile]),
  );

  if (!account) {
    return (
      <View className="flex-1 items-center justify-center bg-ground">
        <ActivityIndicator color={C.inkMuted} />
      </View>
    );
  }

  const locked = !hasAccess(account);
  const paid = isPaid(account);
  const companyName = profile.company || account.companyName || 'Your company';

  // Computed from `account` on every render so the compiler re-derives them
  // when verification or payment state changes. See the note in store/session.
  const canAiMentor = gate(account, 'aiMentor');
  const canRequests = gate(account, 'investorRequests');
  const canProgrammes = gate(account, 'programmes');
  const canReassess = gate(account, 'reassess');

  /**
   * Whether there is an assessment to show at all.
   *
   * A finished audit is the strongest signal; a run in flight counts too, so
   * the card reports progress rather than pretending nothing happened. With
   * neither, a complete stored profile still means they took it — the audit
   * engine simply has not scored it yet.
   */
  const assessed = report !== null || run !== null || isAssessmentComplete(profile);

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
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void refreshHome()} tintColor={colors.inkFaint} />}>
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
                style={{ backgroundColor: colors.blue }}>
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

      <View className="mt-4">
        <NextActionCard
          account={account}
          profile={profile}
          report={report}
          run={run}
          summary={summary}
          investorVisible={visible}
        />
      </View>

      <Eyebrow className="mb-[10px] mt-6">PATH TO PUBLISH</Eyebrow>
      <PublishStrip
        account={account}
        profile={profile}
        report={report}
        run={run}
        summary={summary}
        investorVisible={visible}
      />

      {/* fundability */}
      <Eyebrow className="mb-[10px] mt-6">FUNDABILITY</Eyebrow>
      <ScoreCard
        account={account}
        report={report}
        run={run}
        investorVisible={visible}
        // Only computed when the form is actually complete, so a half-filled
        // profile cannot produce a number that looks like a verdict.
        // `assess(profile)` rather than the store's `liveAssessment()`: that
        // one reads state internally, which looks pure to the React Compiler
        // and gets memoised, so the score would stay frozen after a
        // re-assessment. Passing the profile keeps the dependency visible
        // (AGENTS.md, trap 7).
        provisional={assessed && !report ? assess(profile).score : null}
        assessed={assessed}
      />

      {missingFields.length > 0 ? (
        <>
          <Eyebrow className="mb-[10px] mt-6">GAPS TO FILL</Eyebrow>
          <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
            <Txt className="text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
              The audit still wants: {missingFields.slice(0, 8).join(', ')}
              {missingFields.length > 8 ? ` (+${missingFields.length - 8} more)` : ''}.
            </Txt>
            <View className="mt-3">
              <Button label="Update profile" height={40} variant="secondary" onPress={() => router.push(route('/onboarding'))} />
            </View>
          </View>
        </>
      ) : null}

      {summary ? (
        <>
          <Eyebrow className="mb-[10px] mt-6">READINESS</Eyebrow>
          <Pressable
            onPress={() => router.push(route('/founder/tasks'))}
            className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
            <TxtSemi className="text-[14px]">
              {summary.requiredPassed}/{summary.requiredTotal} required tasks passed
            </TxtSemi>
            <Txt className="mt-1 text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
              {summary.gateCleared
                ? 'Gate cleared — you can publish to dealflow when ready.'
                : `${summary.requiredOpen} required tasks still open. Upload evidence to clear them.`}
            </Txt>
            <Txt className="mt-2 text-[12.5px]" style={{ color: C.blue }}>
              Open tasks →
            </Txt>
          </Pressable>
        </>
      ) : null}

      <Eyebrow className="mb-[10px] mt-6">DEALFLOW VISIBILITY</Eyebrow>
      <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
        <TxtSemi className="text-[14px]">{visible ? 'Published' : 'Not in dealflow'}</TxtSemi>
        <Txt className="mt-1 text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
          {visible
            ? 'Investors can see your summary card. You can unpublish any time.'
            : 'Publishing requires a cleared readiness gate and a confirmed email. The server decides.'}
        </Txt>
        {publishError ? (
          <Txt className="mt-2 text-[12px]" style={{ color: C.red }}>
            {publishError}
          </Txt>
        ) : null}
        <View className="mt-3">
          <Button
            label={visible ? 'Unpublish' : 'Publish to dealflow'}
            height={42}
            variant={visible ? 'secondary' : 'primary'}
            loading={publishBusy}
            onPress={async () => {
              setPublishBusy(true);
              setPublishError(null);
              try {
                if (visible) await api.unpublishProfile();
                else await api.publishProfile();
                setVisible(!visible);
              } catch (e) {
                setPublishError(e instanceof Error ? e.message : 'Could not update visibility.');
              } finally {
                setPublishBusy(false);
              }
            }}
          />
        </View>
      </View>

      {/* Secondary tools — demoted so Home stays a command surface */}
      <Eyebrow className="mb-[10px] mt-6">MORE TOOLS</Eyebrow>
      <View className="flex-row flex-wrap gap-[9px]">
        <ModuleTile
          glyph="✦"
          title="AI mentor"
          subtitle="Coming soon"
          gate={canAiMentor}
          onPress={openGated(canAiMentor, '/founder/ai-mentor')}
        />
        <ModuleTile
          glyph="◈"
          title="Investor interest"
          subtitle={pendingCalls ? `${pendingCalls} awaiting your answer` : 'Requests not live yet'}
          gate={canRequests}
          badge={pendingCalls}
          onPress={openGated(canRequests, '/founder/investors')}
        />
        <ModuleTile
          glyph="◎"
          title="Programmes"
          subtitle="Enrolment not live yet"
          gate={canProgrammes}
          onPress={openGated(canProgrammes, '/founder/programmes')}
        />
        <ModuleTile
          glyph="⟳"
          title="Re-assess"
          subtitle="Update metrics and re-score"
          gate={canReassess}
          onPress={openGated(canReassess, '/onboarding')}
        />
        <ModuleTile
          glyph="⎘"
          title="Assessment"
          subtitle={assessed ? 'Score and action plan' : 'Not taken yet'}
          gate={ALLOWED}
          onPress={() => router.push(route(assessed ? '/results' : '/onboarding'))}
        />
        <ModuleTile
          glyph="◇"
          title={paid ? 'Your plan' : locked ? 'Unlock access' : 'Trial'}
          subtitle={paid ? 'Unlocked — one-off payment' : 'Billing not live yet'}
          gate={ALLOWED}
          onPress={goPaywall}
        />
      </View>
    </ScrollView>
  );
}

/**
 * The Fundability card.
 *
 * Four states, and the distinctions matter more than the layout. A scored
 * audit is the real thing. A run still going is progress, not a score. A
 * complete profile with no audit yet gets the on-device estimate, **labelled**
 * — it is a heuristic over the form, not a verdict. Nothing at all gets the
 * invitation to start.
 *
 * `score: null` from a real audit is its own case: the audit reached a verdict
 * of "not enough to tell", and rendering that as a number would be inventing
 * the one thing it declined to say.
 */
function ScoreCard({
  account,
  report,
  run,
  provisional,
  assessed,
  investorVisible,
}: {
  account: FounderAccount;
  report: AuditReport | null;
  run: AuditRun | null;
  provisional: number | null;
  assessed: boolean;
  investorVisible: boolean;
}) {
  if (!assessed) {
    return (
      <Pressable
        accessibilityRole="button"
        onPress={() => router.push(route('/onboarding'))}
        className="rounded-[12px] border border-line bg-surface-1 p-[16px]">
        <TxtSemi className="text-[14px]">Run your Fundability assessment</TxtSemi>
        <Txt className="mt-[4px] text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
          Five short steps. Investors cannot see you without a score.
        </Txt>
        <Txt className="mt-3 text-[12.5px]" style={{ color: C.blue }}>
          Start assessment →
        </Txt>
      </Pressable>
    );
  }

  const open = () => router.push(route('/results'));

  // An audit that is queued or running has no score yet, and saying so beats
  // showing a stale one.
  if (!report && run && run.status !== 'failed') {
    return (
      <Pressable
        accessibilityRole="button"
        onPress={open}
        className="rounded-[12px] border border-line bg-surface-1 p-[16px]">
        <View className="flex-row items-center gap-2">
          <View className="h-[6px] w-[6px] rounded-full" style={{ backgroundColor: C.blue }} />
          <TxtSemi className="text-[14px]">Your audit is running</TxtSemi>
        </View>
        <Txt className="mt-[5px] text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
          Scoring against rubric {run.rubricVersion}. This takes a few minutes — you can leave the
          app and come back.
        </Txt>
      </Pressable>
    );
  }

  const verdict = report?.fundability ?? null;
  const score = verdict ? verdict.score : provisional;
  const isReal = report !== null;

  // A real audit that could not reach a number.
  if (isReal && score === null) {
    return (
      <Pressable
        accessibilityRole="button"
        onPress={open}
        className="rounded-[12px] border border-line bg-surface-1 p-[16px]">
        <TxtSemi className="text-[14px]">Not enough to tell yet</TxtSemi>
        <Txt className="mt-[5px] text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
          {verdict?.rationale ?? 'The audit could not reach a verdict on what it was given.'}
        </Txt>
        <Txt className="mt-3 text-[12.5px]" style={{ color: C.blue }}>
          See what is missing →
        </Txt>
      </Pressable>
    );
  }

  if (score === null) return null;

  const b = band(score);

  return (
    <Pressable
      accessibilityRole="button"
      onPress={open}
      className="flex-row items-center gap-4 rounded-[12px] border border-line bg-surface-1 p-[16px]">
      <View
        className="h-[62px] w-[62px] items-center justify-center rounded-full"
        style={{ borderWidth: 3, borderColor: isReal ? b.color : C.lineStrong }}>
        <Mono className="text-[22px]" style={{ letterSpacing: -1 }}>
          {score}
        </Mono>
      </View>
      <View className="flex-1">
        <TxtSemi className="text-[14px]" style={{ color: isReal ? b.color : C.inkMuted }}>
          {b.label}
        </TxtSemi>
        <Txt className="mt-[3px] text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
          {!isReal
            ? 'Provisional estimate from your answers — not a FundReady AI audit, and no investor can see it.'
            : investorVisible
              ? 'Published — investors can see your summary card.'
              : hasAccess(account)
                ? 'Hidden from investors until you publish.'
                : 'Unlock access to keep working on your readiness.'}
        </Txt>
      </View>
      <Txt className="text-[13px] text-ink-faint">›</Txt>
    </Pressable>
  );
}
