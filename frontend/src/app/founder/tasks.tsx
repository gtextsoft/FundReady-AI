import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  View,
} from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Eyebrow, Mono, Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { Unavailable } from '@/components/unavailable';
import { api } from '@/api';
import type { EvidenceSubmission, ReadinessSummary, ReadinessTask } from '@/domain/readiness';
import { putToSignedUrl } from '@/lib/upload';
import { C } from '@/theme/tokens';

export default function FounderTasks() {
  const insets = useSafeAreaInsets();
  const { taskId } = useLocalSearchParams<{ taskId?: string }>();
  const [summary, setSummary] = useState<ReadinessSummary | null>(null);
  const [tasks, setTasks] = useState<ReadinessTask[]>([]);
  const [selected, setSelected] = useState<ReadinessTask | null>(null);
  const [evidence, setEvidence] = useState<EvidenceSubmission[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sum, page] = await Promise.all([api.getTasksSummary(), api.listTasks({ limit: 100 })]);
      setSummary(sum);
      setTasks(page.items);
      setError(null);
      if (taskId) {
        const match = page.items.find((t) => t.id === taskId) ?? (await api.getTask(taskId));
        setSelected(match);
        const ev = await api.listEvidence(match.id);
        setEvidence(ev.items);
      }
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  async function openTask(task: ReadinessTask) {
    setSelected(task);
    setUploadMessage(null);
    try {
      const ev = await api.listEvidence(task.id);
      setEvidence(ev.items);
    } catch (e) {
      setEvidence([]);
      setUploadMessage(e instanceof Error ? e.message : 'Could not load evidence.');
    }
  }

  async function uploadEvidence() {
    if (!selected) return;
    const result = await DocumentPicker.getDocumentAsync({
      type: '*/*',
      copyToCacheDirectory: true,
    });
    if (result.canceled) return;
    const file = result.assets[0];
    const contentType = file.mimeType || 'application/octet-stream';
    setUploading(true);
    setUploadMessage(null);
    try {
      const ticket = await api.beginEvidenceUpload(selected.id, {
        filename: file.name,
        contentType,
      });
      const blob = await (await fetch(file.uri)).blob();
      await putToSignedUrl(ticket.uploadUrl, blob, contentType, ticket.maxBytes);
      const submission = await api.completeEvidenceUpload(ticket.evidenceId);
      setEvidence((prev) => [submission, ...prev]);
      setUploadMessage(
        submission.outcome
          ? `Graded: ${submission.outcome.replace(/_/g, ' ')}`
          : 'Uploaded — grading in progress.',
      );
      const refreshed = await api.getTask(selected.id);
      setSelected(refreshed);
      setTasks((prev) => prev.map((t) => (t.id === refreshed.id ? refreshed : t)));
      setSummary(await api.getTasksSummary());
    } catch (e) {
      setUploadMessage(e instanceof Error ? e.message : 'Upload failed.');
    } finally {
      setUploading(false);
    }
  }

  if (loading && !tasks.length && !error) {
    return (
      <View className="flex-1 items-center justify-center bg-ground">
        <ActivityIndicator color={C.inkMuted} />
      </View>
    );
  }

  return (
    <View className="flex-1 bg-ground" style={{ paddingTop: insets.top + 4 }}>
      <View className="flex-row items-center justify-between border-b border-line-soft px-[18px] pb-3">
        <Pressable accessibilityRole="button" onPress={() => router.back()} hitSlop={10}>
          <Txt className="text-[19px] text-ink">←</Txt>
        </Pressable>
        <Mono className="text-[10px] text-ink-faint" style={{ letterSpacing: 1.2 }}>
          READINESS
        </Mono>
        <View className="w-6" />
      </View>

      <ScrollView
        contentContainerStyle={{ paddingHorizontal: 18, paddingTop: 16, paddingBottom: 28 }}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={() => void load()} tintColor={C.inkMuted} />}>
        {error ? (
          <Unavailable title="Tasks could not load" error={error} onRetry={() => void load()} />
        ) : (
          <>
            {summary ? (
              <View className="mb-4 rounded-[12px] border border-line bg-surface-1 p-[14px]">
                <TxtSemi className="text-[14px]">Progress</TxtSemi>
                <Txt className="mt-1 text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
                  {summary.requiredPassed}/{summary.requiredTotal} required passed
                  {summary.gateCleared ? ' · Gate cleared' : ` · ${summary.requiredOpen} still open`}
                  {summary.discoverable ? ' · Discoverable' : ''}
                </Txt>
              </View>
            ) : null}

            {selected ? (
              <View className="mb-5 rounded-[12px] border border-line bg-surface-1 p-[14px]">
                <Pressable onPress={() => setSelected(null)} hitSlop={8}>
                  <Txt className="mb-2 text-[12px] text-ink-faint">← All tasks</Txt>
                </Pressable>
                <TxtSemi className="text-[15px]">{selected.action}</TxtSemi>
                <Txt className="mt-1 text-[12px] text-ink-dim">
                  {selected.dimension} · {selected.requirement} · {selected.status.replace(/_/g, ' ')}
                </Txt>
                <Txt className="mt-2 text-[11px] text-ink-faint">
                  Attempts left: {selected.attemptsRemaining}
                </Txt>
                <View className="mt-3">
                  <Button
                    label={uploading ? 'Uploading…' : 'Upload evidence'}
                    height={42}
                    loading={uploading}
                    disabled={selected.attemptsRemaining <= 0}
                    onPress={() => void uploadEvidence()}
                  />
                </View>
                {uploadMessage ? (
                  <Txt className="mt-2 text-[12px] text-ink-muted">{uploadMessage}</Txt>
                ) : null}
                {evidence.length ? (
                  <View className="mt-4 gap-2">
                    <Eyebrow>SUBMISSIONS</Eyebrow>
                    {evidence.map((e) => (
                      <View key={e.id} className="rounded-[9px] border border-line px-3 py-2">
                        <TxtMed className="text-[12.5px]">{e.filename}</TxtMed>
                        <Txt className="text-[11px] text-ink-dim">
                          {e.outcome ? e.outcome.replace(/_/g, ' ') : e.status}
                        </Txt>
                        {e.reasons?.length ? (
                          <Txt className="mt-1 text-[11px] text-ink-muted">{e.reasons.join(' · ')}</Txt>
                        ) : null}
                      </View>
                    ))}
                  </View>
                ) : null}
              </View>
            ) : null}

            <Eyebrow className="mb-[10px]">TASKS</Eyebrow>
            {!tasks.length ? (
              <Txt className="text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
                Tasks appear after a successful audit. Run an assessment first.
              </Txt>
            ) : (
              <View className="gap-[9px]">
                {tasks.map((t) => (
                  <Pressable
                    key={t.id}
                    onPress={() => void openTask(t)}
                    className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
                    <View className="flex-row items-start justify-between gap-2">
                      <TxtSemi className="flex-1 text-[13.5px]">{t.action}</TxtSemi>
                      {t.isPriority ? (
                        <Mono className="text-[9px]" style={{ color: C.amb }}>
                          PRIORITY
                        </Mono>
                      ) : null}
                    </View>
                    <Txt className="mt-1 text-[11.5px] text-ink-dim">
                      {t.dimension} · {t.requirement} · {t.status.replace(/_/g, ' ')}
                    </Txt>
                  </Pressable>
                ))}
              </View>
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}
