import { useCallback, useState } from 'react';
import { ScrollView, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/button';
import { Eyebrow, Mono, Txt, TxtMed, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { gate as capabilityGate, lockExplanation } from '@/domain/access';
import { gateCopy } from '@/domain/gate-copy';
import { formatSlot, relativeTime, type CallRequest } from '@/domain/notifications';
import { route, VERIFY_EMAIL } from '@/lib/routes';
import { useNotifications } from '@/store/notifications';
import { useSession } from '@/store/session';

/**
 * The founder's side of investor contact: virtual-call requests to answer, and
 * a log of introductions that have come in.
 */
export default function InvestorInterest() {
  const insets = useSafeAreaInsets();
  const account = useSession((s) => s.founderAccount);
  const gate = account
    ? capabilityGate(account, 'investorRequests')
    : ({ allowed: false, reason: 'email' } as const);

  const load = useNotifications((s) => s.load);
  const callRequests = useNotifications((s) => s.callRequests);
  const items = useNotifications((s) => s.items);
  const respond = useNotifications((s) => s.respondToCall);

  useFocusEffect(
    useCallback(() => {
      load('founder');
    }, [load]),
  );

  const pending = callRequests.filter((r) => r.status === 'pending');
  const answered = callRequests.filter((r) => r.status !== 'pending');
  const intros = items.filter((n) => n.kind === 'intro_requested');

  return (
    <ScrollView
      className="flex-1 bg-ground"
      contentContainerStyle={{ paddingTop: insets.top + 8, paddingHorizontal: 18, paddingBottom: 24 }}
      showsVerticalScrollIndicator={false}>
      <TxtSemi className="mb-4 text-[19px]" style={{ letterSpacing: -0.5 }}>
        Requests
      </TxtSemi>
      <Txt className="mb-4 text-[12.5px] text-ink-dim" style={{ lineHeight: 19 }}>
        FundReady AI-mediated call requests and introductions appear here when that loop is live.
      </Txt>

      {!gate.allowed ? (
        <View className="rounded-[12px] border border-line bg-surface-1 p-4">
          <TxtSemi className="text-[14px]">{gateCopy(gate.reason, 'founder').title}</TxtSemi>
          <Txt className="mt-[4px] text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
            {lockExplanation(gate.reason)}
          </Txt>
          <View className="mt-4">
            <Button
              label={gateCopy(gate.reason, 'founder').cta}
              height={42}
              onPress={() => {
                if (gate.reason === 'payment') router.push(route('/founder/paywall'));
                else if (gate.reason === 'email') router.push(VERIFY_EMAIL);
                else router.push(route('/founder/verify'));
              }}
            />
          </View>
        </View>
      ) : (
        <>
          <Eyebrow className="mb-[10px]">AWAITING YOUR ANSWER</Eyebrow>
          {pending.length ? (
            <View className="gap-[9px]">
              {pending.map((r) => (
                <CallCard key={r.id} request={r} onRespond={respond} />
              ))}
            </View>
          ) : (
            <EmptyRow text="No call requests right now. Investors who open your profile can propose a slot." />
          )}

          {answered.length ? (
            <>
              <Eyebrow className="mb-[10px] mt-6">ANSWERED</Eyebrow>
              <View className="gap-[9px]">
                {answered.map((r) => (
                  <View key={r.id} className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
                    <View className="flex-row items-center justify-between">
                      <TxtMed className="text-[13px]">Investor call</TxtMed>
                      <Mono
                        className="text-[10px]"
                        style={{ color: r.status === 'accepted' ? C.grn : C.inkFaint }}>
                        {r.status === 'accepted' ? 'ACCEPTED' : 'DECLINED'}
                      </Mono>
                    </View>
                    <Txt className="mt-[3px] text-[12px] text-ink-muted">{formatSlot(r.proposedAt)}</Txt>
                  </View>
                ))}
              </View>
            </>
          ) : null}

          <Eyebrow className="mb-[10px] mt-6">INTRODUCTION REQUESTS</Eyebrow>
          {intros.length ? (
            <View className="gap-[9px]">
              {intros.map((n) => (
                <View key={n.id} className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
                  <TxtMed className="text-[13px]">{n.title}</TxtMed>
                  <Txt className="mt-[3px] text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
                    {n.body}
                  </Txt>
                  <Mono className="mt-2 text-[10px] text-ink-faint">{relativeTime(n.createdAt)}</Mono>
                </View>
              ))}
            </View>
          ) : (
            <EmptyRow text="No introduction requests yet." />
          )}
        </>
      )}
    </ScrollView>
  );
}

function CallCard({
  request,
  onRespond,
}: {
  request: CallRequest;
  onRespond: (id: string, accept: boolean) => Promise<void>;
}) {
  const [busy, setBusy] = useState<'accept' | 'decline' | null>(null);

  async function answer(accept: boolean) {
    setBusy(accept ? 'accept' : 'decline');
    try {
      await onRespond(request.id, accept);
    } finally {
      setBusy(null);
    }
  }

  return (
    <View className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
      <View className="flex-row items-start justify-between gap-3">
        <View className="flex-1">
          <TxtSemi className="text-[14px]">Virtual call request</TxtSemi>
          <Txt className="mt-[3px] text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
            An investor proposed a slot against interest {request.interestId.slice(0, 8)}…
          </Txt>
        </View>
        <View className="rounded-[5px] border border-line-strong px-2 py-[3px]">
          <Mono className="text-[10px]" style={{ color: C.blue }}>
            CALL
          </Mono>
        </View>
      </View>

      <View className="mt-3 rounded-[9px] border border-line bg-ground px-3 py-[10px]">
        <Txt className="text-[10px] text-ink-faint" style={{ letterSpacing: 0.5 }}>
          PROPOSED SLOT
        </Txt>
        <Mono className="mt-[3px] text-[13px]">{formatSlot(request.proposedAt)}</Mono>
      </View>

      {request.message ? (
        <Txt className="mt-3 text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
          “{request.message}”
        </Txt>
      ) : null}

      <View className="mt-3 flex-row gap-2">
        <View style={{ width: 104 }}>
          <Button
            label="Decline"
            variant="secondary"
            height={42}
            loading={busy === 'decline'}
            disabled={busy !== null}
            onPress={() => answer(false)}
          />
        </View>
        <View className="flex-1">
          <Button
            label="Accept call"
            height={42}
            loading={busy === 'accept'}
            disabled={busy !== null}
            onPress={() => answer(true)}
          />
        </View>
      </View>
    </View>
  );
}

function EmptyRow({ text }: { text: string }) {
  return (
    <View className="rounded-[12px] border border-line bg-surface-1 px-[14px] py-[18px]">
      <Txt className="text-[12.5px] text-ink-dim" style={{ lineHeight: 19 }}>
        {text}
      </Txt>
    </View>
  );
}
