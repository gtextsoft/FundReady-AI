import { useEffect } from 'react';
import { Tabs } from 'expo-router';

import { TabBar } from '@/components/ui/tab-bar';
import { C } from '@/theme/tokens';
import { useInvestor } from '@/store/investor';
import { useNotifications } from '@/store/notifications';

const GLYPHS = {
  index: '▤',
  watchlist: '★',
  alerts: '◔',
  profile: '◎',
};

export default function InvestorTabs() {
  const loadWatchlist = useInvestor((s) => s.loadWatchlist);
  const loadNotifications = useNotifications((s) => s.load);
  const unread = useNotifications((s) => s.unreadCount());

  useEffect(() => {
    loadWatchlist();
    loadNotifications('investor');
  }, [loadWatchlist, loadNotifications]);

  return (
    <Tabs
      tabBar={(props) => <TabBar {...props} glyphs={GLYPHS} badges={{ alerts: unread }} />}
      screenOptions={{ headerShown: false, sceneStyle: { backgroundColor: C.ground } }}>
      <Tabs.Screen name="index" options={{ title: 'Dealflow' }} />
      <Tabs.Screen name="watchlist" options={{ title: 'Watchlist' }} />
      <Tabs.Screen name="alerts" options={{ title: 'Alerts' }} />
      <Tabs.Screen name="profile" options={{ title: 'Profile' }} />
    </Tabs>
  );
}
