import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AuditReportView } from '@/components/founder/audit-report';
import { Mono, Txt } from '@/components/ui/text';
import { Unavailable } from '@/components/unavailable';
import { api } from '@/api';
import type { AuditReport } from '@/domain/audit';
import { C } from '@/theme/tokens';

/**
 * Full founder-tier report after SACI has revealed a run on an interest.
 */
export default function RevealedReportScreen() {
  const insets = useSafeAreaInsets();
  const { interestId, runId } = useLocalSearchParams<{ interestId: string; runId: string }>();
  const [report, setReport] = useState<AuditReport | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!interestId || !runId) return;
    let live = true;
    api
      .getRevealedReport(String(interestId), String(runId))
      .then((r) => {
        if (!live) return;
        setReport(r);
        setError(null);
      })
      .catch((e: unknown) => {
        if (!live) return;
        setError(e);
        setReport(null);
      });
    return () => {
      live = false;
    };
  }, [interestId, runId]);

  return (
    <View className="flex-1 bg-ground">
      <View
        className="flex-row items-center justify-between border-b border-line-soft px-[18px] pb-3"
        style={{ paddingTop: insets.top + 4 }}>
        <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={10}>
          <Txt className="text-[19px] text-ink">←</Txt>
        </Pressable>
        <Mono className="text-[10px] text-ink-faint" style={{ letterSpacing: 1.2 }}>
          REVEALED REPORT
        </Mono>
        <View className="w-5" />
      </View>

      <ScrollView
        className="flex-1"
        contentContainerStyle={{ padding: 18, paddingBottom: insets.bottom + 24 }}
        showsVerticalScrollIndicator={false}>
        {error ? (
          <Unavailable
            title="This report is not available"
            error={error}
            onRetry={() => {
              setError(null);
              setReport(null);
              if (interestId && runId) {
                api
                  .getRevealedReport(String(interestId), String(runId))
                  .then(setReport)
                  .catch(setError);
              }
            }}
          />
        ) : !report ? (
          <View className="items-center py-20">
            <ActivityIndicator color={C.inkMuted} />
          </View>
        ) : (
          <AuditReportView report={report} />
        )}
      </ScrollView>
    </View>
  );
}
