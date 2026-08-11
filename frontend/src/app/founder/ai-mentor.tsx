import { useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, TextInput, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { C, Font } from '@/theme/tokens';
import { api, ApiFailure } from '@/api';

type Message = { id: string; from: 'you' | 'mentor'; text: string };

const SUGGESTIONS = [
  'How do I raise my score?',
  'Are my unit economics good enough?',
  'What will investors push back on?',
];

const OPENER =
  'Ask me about your growth, unit economics, margin, market size or deck and I will answer against your own numbers.';

export default function AiMentor() {
  const insets = useSafeAreaInsets();
  const scrollRef = useRef<ScrollView>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<Message[]>([{ id: 'opener', from: 'mentor', text: OPENER }]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || busy) return;
    setDraft('');
    setBusy(true);
    setMessages((m) => [...m, { id: `q${m.length}`, from: 'you', text: question }]);
    try {
      const answer = await api.askMentor(question);
      setMessages((m) => [...m, { id: `a${m.length}`, from: 'mentor', text: answer }]);
    } catch (e) {
      // Say why there is no answer. Anything else here would be the model
      // making something up, which is the one thing this screen must not do.
      const text =
        e instanceof ApiFailure
          ? e.message
          : 'I could not reach the mentor service. Try again in a moment.';
      setMessages((m) => [...m, { id: `a${m.length}`, from: 'mentor', text }]);
    } finally {
      setBusy(false);
      requestAnimationFrame(() => scrollRef.current?.scrollToEnd({ animated: true }));
    }
  }

  return (
    <KeyboardAvoidingView className="flex-1 bg-obsidian" behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View className="flex-row items-center justify-between border-b border-graphite-soft px-[18px] pb-3" style={{ paddingTop: insets.top + 4 }}>
        <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={10}>
          <Txt className="text-[19px] text-bone">←</Txt>
        </Pressable>
        <Mono className="text-[10px] text-bone-faint" style={{ letterSpacing: 1.2 }}>
          AI MENTOR
        </Mono>
        <View className="w-5" />
      </View>

      <ScrollView
        ref={scrollRef}
        className="flex-1"
        contentContainerStyle={{ padding: 18, gap: 10 }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
        onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}>
        {messages.map((m) => (
          <Animated.View
            key={m.id}
            entering={FadeInDown.duration(220)}
            className={`max-w-[86%] rounded-[13px] px-[13px] py-[10px] ${
              m.from === 'you' ? 'self-end bg-bone' : 'self-start border border-graphite bg-carbon-low'
            }`}>
            <Txt className={`text-[13px] ${m.from === 'you' ? 'text-obsidian' : 'text-bone'}`} style={{ lineHeight: 20 }}>
              {m.text}
            </Txt>
          </Animated.View>
        ))}

        {busy ? (
          <View className="self-start rounded-[13px] border border-graphite bg-carbon-low px-[13px] py-[10px]">
            <Txt className="text-[13px] text-bone-faint">Thinking…</Txt>
          </View>
        ) : null}

        {messages.length === 1 ? (
          <View className="mt-2 gap-[7px]">
            {SUGGESTIONS.map((s) => (
              <Pressable
                key={s}
                accessibilityRole="button"
                onPress={() => send(s)}
                className="self-start rounded-[8px] border border-graphite-strong bg-carbon-low px-3 py-2">
                <Txt className="text-[12.5px] text-bone-secondary">{s}</Txt>
              </Pressable>
            ))}
          </View>
        ) : null}
      </ScrollView>

      <View className="border-t border-graphite-soft bg-obsidian px-[18px] pt-3" style={{ paddingBottom: insets.bottom + 14 }}>
        <View className="flex-row items-center gap-2 rounded-[11px] border border-graphite-strong bg-carbon-low px-[14px]" style={{ minHeight: 46 }}>
          <TextInput
            className="min-w-0 flex-1 text-[14px] text-bone"
            placeholder="Ask about your metrics…"
            placeholderTextColor={C.boneFaint}
            value={draft}
            onChangeText={setDraft}
            onSubmitEditing={() => send(draft)}
            returnKeyType="send"
            multiline
            style={{ fontFamily: Font.regular, paddingVertical: 12 }}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Send"
            onPress={() => send(draft)}
            disabled={!draft.trim() || busy}
            hitSlop={8}>
            <TxtSemi className="text-[13px]" style={{ color: draft.trim() && !busy ? C.bone : C.boneFaint }}>
              Send
            </TxtSemi>
          </Pressable>
        </View>
        <Txt className="mt-2 text-center text-[10.5px] text-bone-ghost">
          Guidance from your declared metrics. Not investment advice.
        </Txt>
      </View>
    </KeyboardAvoidingView>
  );
}
