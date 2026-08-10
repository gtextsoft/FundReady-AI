import { Pressable, Text, View } from 'react-native';
import type { Tabs } from 'expo-router';
import type { ComponentProps } from 'react';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Mono, Txt } from './text';
import { useThemeColors } from '@/theme/use-theme-colors';

/**
 * Expo Router 57 vendors its own copy of bottom-tabs, so there is no
 * `@react-navigation/bottom-tabs` to import `BottomTabBarProps` from. Read the
 * type off the component instead of deep-importing a build path.
 */
export type TabBarProps = Parameters<NonNullable<ComponentProps<typeof Tabs>['tabBar']>>[0];

/**
 * Shared bottom bar for both sides of the marketplace.
 *
 * React Navigation's default web bar clips the label under our 58px height,
 * and the prototype's bar is simple enough to own outright: a glyph over a
 * 10px label, equal columns, one hairline on top. `badges` puts an unread
 * count on a tab — used by the notification centre on both sides.
 */
export function TabBar({
  state,
  descriptors,
  navigation,
  glyphs,
  badges,
}: TabBarProps & {
  /** Route name → glyph. */
  glyphs: Record<string, string>;
  /** Route name → unread count. Zero or missing renders nothing. */
  badges?: Record<string, number>;
}) {
  const insets = useSafeAreaInsets();
  const colors = useThemeColors();

  return (
    <View
      className="flex-row border-t border-line-soft bg-ground px-3 pt-2"
      style={{ paddingBottom: insets.bottom + 10 }}>
      {state.routes.map((route, index) => {
        const focused = state.index === index;
        const { options } = descriptors[route.key];
        const label = options.title ?? route.name;
        const color = focused ? colors.ink : colors.inkFaint;
        const badge = badges?.[route.name] ?? 0;

        return (
          <Pressable
            key={route.key}
            accessibilityRole="tab"
            accessibilityState={{ selected: focused }}
            accessibilityLabel={badge ? `${label}, ${badge} unread` : String(label)}
            hitSlop={6}
            onPress={() => {
              const event = navigation.emit({ type: 'tabPress', target: route.key, canPreventDefault: true });
              if (!focused && !event.defaultPrevented) navigation.navigate(route.name);
            }}
            className="min-h-[44px] flex-1 items-center justify-center gap-[3px] py-[6px]">
            <View>
              <Text style={{ fontSize: 15, color }}>{glyphs[route.name] ?? '•'}</Text>
              {badge > 0 ? (
                <View
                  className="absolute -right-[9px] -top-[4px] h-[14px] min-w-[14px] items-center justify-center rounded-full px-[3px]"
                  style={{ backgroundColor: colors.blue }}>
                  <Mono className="text-[8px] text-white">{badge > 9 ? '9+' : badge}</Mono>
                </View>
              ) : null}
            </View>
            <Txt className="text-[10px]" style={{ color }}>
              {label}
            </Txt>
          </Pressable>
        );
      })}
    </View>
  );
}
