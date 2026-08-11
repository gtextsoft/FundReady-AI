import { useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, TextInput, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { C, Font } from '@/theme/tokens';
import { api, ApiFailure } from '@/api';
import type { MentorCitation } from '@/domain/mentor';

type Message = {
  id: string;
  from: 'you' | 'analyst';
  text: string;
  citations?: MentorCitation[];
};

const SUGGESTIONS = [
  'What stands out in the summary?',
  'How does fundability look?',
  'What would you ask the founder next?',
];

const OPENER =
  'I only see the summary card for this startup — scores, sector, stage, country. Ask about that. I will not invent full-report figures.';

export default function InvestorAnalyst() {
  const insets = useSafeAreaInsets();
  const { id } = useLocalSearchParams<{ id: string }>();
  const scrollRef = useRef<ScrollView>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    { id: 'opener', from: 'analyst', text: OPENER },
  ]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || busy || !id) return;
    setDraft('');
    setBusy(true);
    setMessages((m) => [...m, { id: `q${m.length}`, from: 'you', text: question }]);
    try {
      const history = messages
        .filter((m) => m.id !== 'opener')
        .slice(-10)
        .map((m) => ({
          role: (m.from === 'you' ? 'user' : 'assistant') as 'user' | 'assistant',
          content: m.text,
        }));
      const result = await api.chatAnalyst(String(id), { message: question, history });
      setMessages((m) => [
        ...m,
        {
          id: `a${m.length}`,
          from: 'analyst',
          text: result.reply,
          citations: result.citations,
        },
      ]);
    } catch (e) {
      const errText =
        e instanceof ApiFailure
          ? e.message
          : 'I could not reach the analyst. Try again in a moment.';
      setMessages((m) => [...m, { id: `a${m.length}`, from: 'analyst', text: errText }]);
    } finally {
      setBusy(false);
      requestAnimationFrame(() => scrollRef.current?.scrollToEnd({ animated: true }));
    }
  }

  return (
    <KeyboardAvoidingView className="flex-1 bg-ground" behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View
        className="flex-row items-center justify-between border-b border-line-soft px-[18px] pb-3"
        style={{ paddingTop: insets.top + 4 }}>
        <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={10}>
          <Txt className="text-[19px] text-ink">←</Txt>
        </Pressable>
        <Mono className="text-[10px] text-ink-faint" style={{ letterSpacing: 1.2 }}>
          AI ANALYST
        </Mono>
        <View className="w-5" />
      </View>

      <ScrollView
        ref={scrollRef}
        className="flex-1"
        contentContainerStyle={{ padding: 18, paddingBottom: 12, gap: 12 }}
        onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}>
        {messages.map((m) => (
          <View
            key={m.id}
            className={`max-w-[92%] rounded-[12px] px-3.5 py-3 ${
              m.from === 'you' ? 'self-end bg-ink' : 'self-start border border-line bg-surface-1'
            }`}>
            <Txt
              className={`text-[13.5px] ${m.from === 'you' ? 'text-ground' : 'text-ink'}`}
              style={{ lineHeight: 20 }}>
              {m.text}
            </Txt>
            {m.citations?.length ? (
              <Mono className="mt-2 text-[9.5px] text-ink-faint" style={{ letterSpacing: 0.4 }}>
                {m.citations.map((c) => `${c.kind}:${c.ref}`).join(' · ')}
              </Mono>
            ) : null}
          </View>
        ))}
      </ScrollView>

      <View className="border-t border-line-soft px-[18px] pt-3" style={{ paddingBottom: insets.bottom + 12 }}>
        <View className="mb-2 flex-row flex-wrap gap-[7px]">
          {SUGGESTIONS.map((s) => (
            <Pressable
              key={s}
              onPress={() => send(s)}
              className="rounded-[8px] border border-line-strong bg-surface-1 px-[10px] py-[6px]">
              <Txt className="text-[11.5px] text-ink-muted">{s}</Txt>
            </Pressable>
          ))}
        </View>
        <View className="flex-row items-end gap-2">
          <View className="min-h-[46px] flex-1 rounded-[11px] border border-line-strong bg-surface-1 px-3 py-2">
            <TextInput
              className="text-[14px] text-ink"
              placeholder="Ask about this summary…"
              placeholderTextColor={C.inkFaint}
              value={draft}
              onChangeText={setDraft}
              multiline
              style={{ fontFamily: Font.regular, maxHeight: 100 }}
            />
          </View>
          <Button label="Send" height={46} loading={busy} onPress={() => send(draft)} />
        </View>
        <TxtSemi className="mt-2 text-center text-[10px] text-ink-faint">
          Summary tier only · never invents full-report numbers
        </TxtSemi>
      </View>
    </KeyboardAvoidingView>
  );
}
