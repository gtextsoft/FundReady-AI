import { useState } from 'react';
import { Linking, Pressable, ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';

import { Button } from '@/components/ui/button';
import { Mono, Txt } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { daysLeftInTrial, hasAccess, isPaid, TRIAL_DAYS } from '@/domain/access';
import { UNLOCK_BENEFITS, UNLOCK_PRICE } from '@/domain/pricing';
import { Unavailable } from '@/components/unavailable';
import { api, type PaymentReceipt } from '@/api';
import { useSession } from '@/store/session';

/**
 * One-off unlock via Stripe Checkout (backend D21).
 *
 * The button opens hosted Checkout. Entitlement is granted only after the
 * Stripe webhook fires — refresh the account when the founder returns.
 */
export default function Paywall() {
  const insets = useSafeAreaInsets();
  const account = useSession((s) => s.founderAccount);
  const refreshAccount = useSession((s) => s.refreshAccount);
  const [busy, setBusy] = useState(false);
  const [receipt, setReceipt] = useState<PaymentReceipt | null>(null);
  const [checkoutOpened, setCheckoutOpened] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (!account) return <View className="flex-1 bg-ground" />;

  const paid = isPaid(account) || receipt !== null;
  const locked = !hasAccess(account);
  const days = daysLeftInTrial(account);

  async function pay() {
    setBusy(true);
    setError(null);
    try {
      const session = await api.purchaseUnlock();
      const opened = await Linking.openURL(session.checkoutUrl);
      setCheckoutOpened(opened !== false);
      // Webhook grants access asynchronously; refresh after the browser returns.
      await refreshAccount();
      const paidReceipt = await api.getUnlockReceipt();
      if (paidReceipt) setReceipt(paidReceipt);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function refreshAfterCheckout() {
    setBusy(true);
    setError(null);
    try {
      await refreshAccount();
      const paidReceipt = await api.getUnlockReceipt();
      if (paidReceipt) setReceipt(paidReceipt);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <View className="flex-1 bg-ground">
      <View className="flex-row items-center justify-between px-[18px] pb-3" style={{ paddingTop: insets.top + 4 }}>
        <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={10}>
          <Txt className="text-[19px] text-ink">←</Txt>
        </Pressable>
        <Mono className="text-[10px] text-ink-faint" style={{ letterSpacing: 1.2 }}>
          {paid ? 'YOUR PLAN' : 'UNLOCK'}
        </Mono>
        <View className="w-5" />
      </View>

      <ScrollView
        className="flex-1"
        contentContainerStyle={{ paddingHorizontal: 18, paddingBottom: 24 }}
        showsVerticalScrollIndicator={false}>
        <View className="overflow-hidden rounded-[14px] border border-line">
          <LinearGradient colors={['#0f0f0f', '#0a0a0a']} className="items-center px-5 py-7">
            <Mono className="text-[9.5px]" style={{ letterSpacing: 1.2, color: paid ? C.grn : C.amb }}>
              {paid ? 'UNLOCKED' : locked ? 'TRIAL ENDED' : `TRIAL · ${days} ${days === 1 ? 'DAY' : 'DAYS'} LEFT`}
            </Mono>

            <View className="mt-4 flex-row items-baseline gap-1">
              <Mono className="text-[42px]" style={{ letterSpacing: -2 }}>
                {UNLOCK_PRICE.label}
              </Mono>
              <Txt className="text-[13px] text-ink-faint">once</Txt>
            </View>
            <Txt className="mt-2 text-center text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
              {paid
                ? 'Paid. Your access does not expire and there is nothing to renew.'
                : 'A single payment. No subscription, no renewal, no expiry.'}
            </Txt>
          </LinearGradient>
        </View>

        <View className="mt-5 gap-[10px]">
          {UNLOCK_BENEFITS.map((b) => (
            <View key={b} className="flex-row gap-[10px]">
              <Txt className="text-[12.5px]" style={{ color: paid ? C.grn : C.ink }}>
                ✓
              </Txt>
              <Txt className="flex-1 text-[13px]" style={{ lineHeight: 20 }}>
                {b}
              </Txt>
            </View>
          ))}
        </View>

        {error ? <Unavailable title="Could not start checkout" error={error} className="mt-6" /> : null}

        {checkoutOpened && !paid ? (
          <View className="mt-6 rounded-[12px] border border-line p-[14px]">
            <Mono className="text-[9px] text-ink-faint" style={{ letterSpacing: 1.2 }}>
              CHECKOUT OPENED
            </Mono>
            <Txt className="mt-2 text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
              Complete payment in the browser, then tap below to refresh your access.
            </Txt>
          </View>
        ) : null}

        {receipt ? (
          <View
            className="mt-6 rounded-[12px] p-[14px]"
            style={{ borderWidth: 1, borderColor: 'rgba(12,206,107,0.30)', backgroundColor: 'rgba(12,206,107,0.07)' }}>
            <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: C.grn }}>
              PAYMENT RECEIVED
            </Mono>
            <Txt className="mt-2 text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
              Reference {receipt.reference}.
            </Txt>
          </View>
        ) : null}

        {!paid ? (
          <Txt className="mt-6 text-[11px] text-ink-faint" style={{ lineHeight: 17 }}>
            Every founder gets {TRIAL_DAYS} days of full access from signup. After that, this one-off payment keeps
            everything on permanently.
          </Txt>
        ) : null}
      </ScrollView>

      <View className="border-t border-line-soft bg-ground px-[18px] pt-3" style={{ paddingBottom: insets.bottom + 14 }}>
        {paid ? (
          <Button label="Back to dashboard" variant="secondary" height={48} onPress={() => router.back()} />
        ) : checkoutOpened ? (
          <Button label="I've paid — refresh access" height={48} loading={busy} onPress={refreshAfterCheckout} />
        ) : (
          <Button label={`Pay ${UNLOCK_PRICE.label} once`} height={48} loading={busy} onPress={pay} />
        )}
      </View>
    </View>
  );
}
