import { Pressable, View } from 'react-native';
import { router } from 'expo-router';

import { Mono, Txt } from '@/components/ui/text';
import { useThemeColors } from '@/theme/use-theme-colors';
import type { AuditReport, AuditRun } from '@/domain/audit';
import type { ReadinessSummary } from '@/domain/readiness';
import type { FounderAccount, FounderProfile } from '@/domain/types';
import { route, VERIFY_EMAIL } from '@/lib/routes';
import { isAssessmentComplete } from '@/store/founder';

type Node = {
  key: string;
  label: string;
  done: boolean;
  onPress: () => void;
};

/** Linear publish story: Email → Score → Tasks → Registration → Publish. */
export function PublishStrip({
  account,
  profile,
  report,
  run,
  summary,
  investorVisible,
  onPublishFocus,
}: {
  account: FounderAccount;
  profile: FounderProfile;
  report: AuditReport | null;
  run: AuditRun | null;
  summary: ReadinessSummary | null;
  investorVisible: boolean;
  onPublishFocus?: () => void;
}) {
  const colors = useThemeColors();
  const scored = report !== null || (run !== null && run.status === 'succeeded') || isAssessmentComplete(profile);
  const tasksDone = summary?.gateCleared ?? false;
  const registered = Boolean(profile.legalName?.trim() && profile.registrationNumber?.trim());

  const nodes: Node[] = [
    {
      key: 'email',
      label: 'Email',
      done: account.emailVerified,
      onPress: () => router.push(VERIFY_EMAIL),
    },
    {
      key: 'score',
      label: 'Score',
      done: scored,
      onPress: () => router.push(route(scored ? '/results' : '/onboarding')),
    },
    {
      key: 'tasks',
      label: 'Tasks',
      done: tasksDone,
      onPress: () => router.push(route('/founder/tasks')),
    },
    {
      key: 'reg',
      label: 'Registration',
      done: registered,
      onPress: () => router.push(route('/founder/verify')),
    },
    {
      key: 'publish',
      label: 'Publish',
      done: investorVisible,
      onPress: () => onPublishFocus?.(),
    },
  ];

  return (
    <View className="rounded-[12px] border border-line bg-surface-1 px-3 py-3">
      <View className="flex-row items-center justify-between">
        {nodes.map((node, i) => (
          <View key={node.key} className="flex-1 flex-row items-center">
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`${node.label}${node.done ? ', done' : ', incomplete'}`}
              onPress={node.onPress}
              className="flex-1 items-center gap-1">
              <View
                className="h-[22px] w-[22px] items-center justify-center rounded-full"
                style={{
                  backgroundColor: node.done ? colors.grn : colors.surface3,
                  borderWidth: 1,
                  borderColor: node.done ? colors.grn : colors.lineStrong,
                }}>
                <Mono className="text-[10px]" style={{ color: node.done ? colors.ground : colors.inkMuted }}>
                  {node.done ? '✓' : String(i + 1)}
                </Mono>
              </View>
              <Txt className="text-[9.5px] text-ink-dim" numberOfLines={1}>
                {node.label}
              </Txt>
            </Pressable>
            {i < nodes.length - 1 ? (
              <View className="mb-4 h-[1px] w-[6px]" style={{ backgroundColor: colors.lineStrong }} />
            ) : null}
          </View>
        ))}
      </View>
    </View>
  );
}
