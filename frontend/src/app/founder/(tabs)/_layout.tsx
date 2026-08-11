import { useEffect } from 'react';
import { Tabs } from 'expo-router';

import { TabBar } from '@/components/ui/tab-bar';
import { useThemeColors } from '@/theme/use-theme-colors';
import { useNotifications } from '@/store/notifications';

const GLYPHS = {
  index: '⌂',
  investors: '◈',
  alerts: '◔',
  profile: '◎',
};

export default function FounderTabs() {
  const colors = useThemeColors();
  const load = useNotifications((s) => s.load);
  const pending = useNotifications((s) => s.pendingCalls().length);
  const unread = useNotifications((s) => s.unreadCount());

  useEffect(() => {
    load('founder');
  }, [load]);

  return (
    <Tabs
      tabBar={(props) => (
        <TabBar
          {...props}
          glyphs={GLYPHS}
          badges={{ alerts: unread, investors: pending }}
        />
      )}
      screenOptions={{ headerShown: false, sceneStyle: { backgroundColor: colors.ground } }}>
      <Tabs.Screen name="index" options={{ title: 'Home' }} />
      <Tabs.Screen name="investors" options={{ title: 'Requests' }} />
      <Tabs.Screen name="alerts" options={{ title: 'Alerts' }} />
      <Tabs.Screen name="profile" options={{ title: 'Profile' }} />
    </Tabs>
  );
}
