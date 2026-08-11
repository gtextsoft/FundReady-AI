import { useEffect } from 'react';
import { Tabs } from 'expo-router';

import { TabBar } from '@/components/ui/tab-bar';
import { C } from '@/theme/tokens';
import { useNotifications } from '@/store/notifications';

const GLYPHS = {
  index: '⌂',
  investors: '◈',
  alerts: '◔',
  profile: '◎',
};

export default function FounderTabs() {
  const load = useNotifications((s) => s.load);
  const unread = useNotifications((s) => s.unreadCount());
  const pending = useNotifications((s) => s.pendingCalls().length);

  useEffect(() => {
    load('founder');
  }, [load]);

  return (
    <Tabs
      tabBar={(props) => <TabBar {...props} glyphs={GLYPHS} badges={{ alerts: unread, investors: pending }} />}
      screenOptions={{ headerShown: false, sceneStyle: { backgroundColor: C.obsidian } }}>
      <Tabs.Screen name="index" options={{ title: 'Home' }} />
      <Tabs.Screen name="investors" options={{ title: 'Investors' }} />
      <Tabs.Screen name="alerts" options={{ title: 'Alerts' }} />
      <Tabs.Screen name="profile" options={{ title: 'Profile' }} />
    </Tabs>
  );
}
