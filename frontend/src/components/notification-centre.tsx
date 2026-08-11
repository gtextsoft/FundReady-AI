import { useCallback } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { Unavailable } from '@/components/unavailable';
import { notificationColor, relativeTime, type AppNotification } from '@/domain/notifications';
import { route } from '@/lib/routes';
import { useNotifications } from '@/store/notifications';
import type { Role } from '@/api';
import { useThemeColors } from '@/theme/use-theme-colors';

/**
 * The alerts tab, shared by both sides.
 *
 * Opening the tab marks everything read — the badge exists to pull you in
 * once, not to be dismissed item by item.
 */
export function NotificationCentre({ audience }: { audience: Role }) {
  const insets = useSafeAreaInsets();
  const colors = useThemeColors();
  const load = useNotifications((s) => s.load);
  const markAllRead = useNotifications((s) => s.markAllRead);
  const items = useNotifications((s) => s.items);
  const error = useNotifications((s) => s.error);

  useFocusEffect(
    useCallback(() => {
      let alive = true;
      load(audience).then(() => {
        if (alive) markAllRead();
      });
      return () => {
        alive = false;
      };
    }, [load, markAllRead, audience]),
  );

  return (
    <ScrollView
      className="flex-1 bg-ground"
      contentContainerStyle={{ paddingTop: insets.top + 8, paddingHorizontal: 18, paddingBottom: 24 }}
      showsVerticalScrollIndicator={false}>
      <TxtSemi className="mb-4 text-[19px]" style={{ letterSpacing: -0.5 }}>
        Alerts
      </TxtSemi>

      {error ? (
        <Unavailable title="Could not load alerts" error={error} />
      ) : items.length ? (
        <View className="gap-[9px]">
          {items.map((n) => (
            <NotificationRow key={n.id} notification={n} audience={audience} />
          ))}
        </View>
      ) : (
        <View className="items-center gap-[11px] px-6 py-[70px]">
          <View
            className="h-[42px] w-[42px] items-center justify-center rounded-[11px]"
            style={{ borderWidth: 1, borderStyle: 'dashed', borderColor: colors.lineDash }}>
            <Txt className="text-[16px] text-ink-ghost">◔</Txt>
          </View>
          <TxtSemi className="text-center text-[14px]">Nothing yet</TxtSemi>
          <Txt className="text-center text-[12.5px] text-ink-dim" style={{ lineHeight: 19 }}>
            {audience === 'founder'
              ? 'Alerts will appear here when investors engage — introductions, call requests, and verification updates.'
              : 'Alerts will appear here when companies you watch change or FundReady AI answers an interest.'}
          </Txt>
        </View>
      )}
    </ScrollView>
  );
}

function NotificationRow({ notification, audience }: { notification: AppNotification; audience: Role }) {
  const n = notification;

  // A call request is answered on the founder's Investors tab; everything with
  // a startup attached opens that company on the investor side.
  const target =
    n.callRequestId && audience === 'founder'
      ? '/founder/investors'
      : n.startupId && audience === 'investor'
        ? `/investor/company/${n.startupId}`
        : null;

  const body = (
    <>
      <View className="mt-[6px] h-[6px] w-[6px] rounded-full" style={{ backgroundColor: notificationColor(n.kind) }} />
      <View className="flex-1">
        <TxtSemi className="text-[13.5px]">{n.title}</TxtSemi>
        <Txt className="mt-[3px] text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
          {n.body}
        </Txt>
        <View className="mt-2 flex-row items-center justify-between">
          <Mono className="text-[10px] text-ink-faint">{relativeTime(n.createdAt)}</Mono>
          {target ? (
            <Txt className="text-[11.5px] text-ink-muted">
              {n.callRequestId ? 'Answer →' : 'View company →'}
            </Txt>
          ) : null}
        </View>
      </View>
    </>
  );

  const className = `flex-row gap-[10px] rounded-[12px] border bg-surface-1 p-[14px] ${
    n.read ? 'border-line' : 'border-line-strong'
  }`;

  if (!target) return <View className={className}>{body}</View>;

  return (
    <Pressable accessibilityRole="button" accessibilityLabel={n.title} onPress={() => router.push(route(target))} className={className}>
      {body}
    </Pressable>
  );
}
