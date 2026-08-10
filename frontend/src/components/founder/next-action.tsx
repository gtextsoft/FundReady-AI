import { View } from 'react-native';
import { router } from 'expo-router';

import { Button } from '@/components/ui/button';
import { Eyebrow, Txt, TxtSemi } from '@/components/ui/text';
import type { AuditReport, AuditRun } from '@/domain/audit';
import type { ReadinessSummary } from '@/domain/readiness';
import type { FounderAccount, FounderProfile } from '@/domain/types';
import { route, VERIFY_EMAIL } from '@/lib/routes';
import { isAssessmentComplete } from '@/store/founder';

type NextAction = {
  eyebrow: string;
  title: string;
  body: string;
  cta: string;
  /** App path or verify-email destination. */
  href: string;
};

export function resolveNextAction(input: {
  account: FounderAccount;
  profile: FounderProfile;
  report: AuditReport | null;
  run: AuditRun | null;
  summary: ReadinessSummary | null;
  investorVisible: boolean;
}): NextAction {
  const { account, profile, report, run, summary, investorVisible } = input;
  const assessed = report !== null || run !== null || isAssessmentComplete(profile);

  if (!account.emailVerified) {
    return {
      eyebrow: 'NEXT STEP',
      title: 'Confirm your email',
      body: 'Profile saves, audits, and publishing require a confirmed address.',
      cta: 'Confirm email',
      href: String(VERIFY_EMAIL),
    };
  }

  if (!assessed) {
    return {
      eyebrow: 'NEXT STEP',
      title: 'Run your Fundability assessment',
      body: 'Five short steps. Investors cannot see you without a score.',
      cta: 'Start assessment',
      href: '/onboarding',
    };
  }

  if (!report && run && run.status !== 'failed' && run.status !== 'succeeded') {
    return {
      eyebrow: 'IN PROGRESS',
      title: 'Your audit is running',
      body: 'This usually takes a few minutes. You can leave and come back.',
      cta: 'View status',
      href: '/results',
    };
  }

  if (summary && !summary.gateCleared) {
    return {
      eyebrow: 'NEXT STEP',
      title: `Close ${summary.requiredOpen} readiness task${summary.requiredOpen === 1 ? '' : 's'}`,
      body: 'Clear required tasks with evidence before you can publish to dealflow.',
      cta: 'Open tasks',
      href: '/founder/tasks',
    };
  }

  if (!investorVisible) {
    return {
      eyebrow: 'NEXT STEP',
      title: 'Publish to dealflow',
      body: 'Your readiness gate is clear. Publish when you want investors to see your summary.',
      cta: 'Review visibility',
      href: '/founder',
    };
  }

  return {
    eyebrow: 'YOU ARE LIVE',
    title: 'Published in dealflow',
    body: 'Keep tasks current and re-assess when your metrics change.',
    cta: 'View results',
    href: '/results',
  };
}

export function NextActionCard({
  account,
  profile,
  report,
  run,
  summary,
  investorVisible,
}: {
  account: FounderAccount;
  profile: FounderProfile;
  report: AuditReport | null;
  run: AuditRun | null;
  summary: ReadinessSummary | null;
  investorVisible: boolean;
}) {
  const action = resolveNextAction({ account, profile, report, run, summary, investorVisible });

  return (
    <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
      <Eyebrow>{action.eyebrow}</Eyebrow>
      <TxtSemi className="mt-2 text-[16px]" style={{ letterSpacing: -0.3 }}>
        {action.title}
      </TxtSemi>
      <Txt className="mt-1 text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
        {action.body}
      </Txt>
      <View className="mt-3">
        <Button
          label={action.cta}
          height={42}
          onPress={() => {
            if (action.href === String(VERIFY_EMAIL)) router.push(VERIFY_EMAIL);
            else if (action.href === '/founder') {
              /* stay — publish controls are below */
            } else router.push(route(action.href));
          }}
        />
      </View>
    </View>
  );
}
