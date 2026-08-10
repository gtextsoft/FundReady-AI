import { useEffect, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, TextInput, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { Button } from '@/components/ui/button';
import { C, Font } from '@/theme/tokens';
import { api, ApiFailure } from '@/api';
import type { MentorCitation } from '@/domain/mentor';
import { FOUNDER_HOME } from '@/lib/routes';

type Message = {
  id: string;
  from: 'you' | 'mentor';
  text: string;
  citations?: MentorCitation[];
};

const SUGGESTIONS = [
  'How do I raise my score?',
  'What should I fix first?',
  'What will investors push back on?',
];

const OPENER =
  'Ask me about your audit, gaps, or readiness tasks. I answer only from your own report and evidence — I will not invent numbers.';

export default function AiMentor() {
  const insets = useSafeAreaInsets();
  const scrollRef = useRef<ScrollView>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState<'loading' | 'no-audit' | 'ok'>('loading');
  const [messages, setMessages] = useState<Message[]>([{ id: 'opener', from: 'mentor', text: OPENER }]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const runs = await api.listAuditRuns();
        const ok = runs.some((r) => r.status === 'succeeded');
        if (!cancelled) setReady(ok ? 'ok' : 'no-audit');
      } catch {
        if (!cancelled) setReady('no-audit');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function send(text: string) {
    const question = text.trim();
    if (!question || busy || ready !== 'ok') return;
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
      const result = await api.chatMentor({ message: question, history });
      setMessages((m) => [
        ...m,
        {
          id: `a${m.length}`,
          from: 'mentor',
          text: result.reply,
          citations: result.citations,
        },
      ]);
    } catch (e) {
      const errText =
        e instanceof ApiFailure
          ? e.message
          : 'I could not reach the mentor service. Try again in a moment.';
      setMessages((m) => [...m, { id: `a${m.length}`, from: 'mentor', text: errText }]);
    } finally {
      setBusy(false);
      requestAnimationFrame(() => scrollRef.current?.scrollToEnd({ animated: true }));
    }
  }

  return (
    <KeyboardAvoidingView className="flex-1 bg-ground" behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View className="flex-row items-center justify-between border-b border-line-soft px-[18px] pb-3" style={{ paddingTop: insets.top + 4 }}>
        <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={10}>
          <Txt className="text-[19px] text-ink">←</Txt>
        </Pressable>
        <Mono className="text-[10px] text-ink-faint" style={{ letterSpacing: 1.2 }}>
          AI MENTOR
        </Mono>
        <View className="w-5" />
      </View>

      {ready === 'no-audit' ? (
        <View className="flex-1 items-center justify-center px-8">
          <Mono className="mb-3 text-[10px] text-ink-faint" style={{ letterSpacing: 1.2 }}>
            NO AUDIT YET
          </Mono>
          <TxtSemi className="mb-2 text-center text-[17px]" style={{ letterSpacing: -0.3 }}>
            Run an audit first
          </TxtSemi>
          <Txt className="mb-6 text-center text-[13px] text-ink-muted" style={{ lineHeight: 20 }}>
            The mentor only answers from your succeeded audit report and readiness tasks. Without
            that context it would be guessing — and it will not guess.
          </Txt>
          <Button label="Go to dashboard" variant="secondary" onPress={() => router.replace(FOUNDER_HOME)} />
        </View>
      ) : (
        <>
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
                  m.from === 'you' ? 'self-end bg-ink' : 'self-start border border-line bg-surface-1'
                }`}>
                <Txt className={`text-[13px] ${m.from === 'you' ? 'text-ground' : 'text-ink'}`} style={{ lineHeight: 20 }}>
                  {m.text}
                </Txt>
                {m.citations && m.citations.length > 0 ? (
                  <View className="mt-2 flex-row flex-wrap gap-1.5">
                    {m.citations.map((c, i) => (
                      <View
                        key={`${c.kind}-${c.ref}-${i}`}
                        className="rounded-[5px] border border-line-soft px-1.5 py-0.5">
                        <Mono className="text-[9px] text-ink-faint">
                          {c.kind}:{c.ref}
                        </Mono>
                      </View>
                    ))}
                  </View>
                ) : null}
              </Animated.View>
            ))}

            {busy || ready === 'loading' ? (
              <View className="self-start rounded-[13px] border border-line bg-surface-1 px-[13px] py-[10px]">
                <Txt className="text-[13px] text-ink-faint">
                  {ready === 'loading' ? 'Checking your audit…' : 'Thinking…'}
                </Txt>
              </View>
            ) : null}

            {ready === 'ok' && messages.length === 1 ? (
              <View className="mt-2 gap-[7px]">
                {SUGGESTIONS.map((s) => (
                  <Pressable
                    key={s}
                    accessibilityRole="button"
                    onPress={() => send(s)}
                    className="self-start rounded-[8px] border border-line-strong bg-surface-1 px-3 py-2">
                    <Txt className="text-[12.5px] text-ink-muted">{s}</Txt>
                  </Pressable>
                ))}
              </View>
            ) : null}
          </ScrollView>

          <View className="border-t border-line-soft bg-ground px-[18px] pt-3" style={{ paddingBottom: insets.bottom + 14 }}>
            <View className="flex-row items-center gap-2 rounded-[11px] border border-line-strong bg-surface-1 px-[14px]" style={{ minHeight: 46 }}>
              <TextInput
                className="min-w-0 flex-1 text-[14px] text-ink"
                placeholder="Ask about your audit…"
                placeholderTextColor={C.inkFaint}
                value={draft}
                onChangeText={setDraft}
                onSubmitEditing={() => send(draft)}
                returnKeyType="send"
                multiline
                editable={ready === 'ok' && !busy}
                style={{ fontFamily: Font.regular, paddingVertical: 12 }}
              />
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Send"
                onPress={() => send(draft)}
                disabled={!draft.trim() || busy || ready !== 'ok'}
                hitSlop={8}>
                <TxtSemi className="text-[13px]" style={{ color: draft.trim() && !busy && ready === 'ok' ? C.ink : C.inkFaint }}>
                  Send
                </TxtSemi>
              </Pressable>
            </View>
            <Txt className="mt-2 text-center text-[10.5px] text-ink-ghost">
              Grounded in your audit and tasks. Not investment advice.
            </Txt>
          </View>
        </>
      )}
    </KeyboardAvoidingView>
  );
}
