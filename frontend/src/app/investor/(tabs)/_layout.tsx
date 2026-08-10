import { useEffect } from 'react';
import { Tabs } from 'expo-router';

import { TabBar } from '@/components/ui/tab-bar';
import { useThemeColors } from '@/theme/use-theme-colors';
import { useInvestor } from '@/store/investor';
import { useNotifications } from '@/store/notifications';

const GLYPHS = {
  index: '▤',
  watchlist: '★',
  alerts: '◔',
  profile: '◎',
};

export default function InvestorTabs() {
  const colors = useThemeColors();
  const loadWatchlist = useInvestor((s) => s.loadWatchlist);
  const loadNotifications = useNotifications((s) => s.load);

  useEffect(() => {
    loadWatchlist();
    loadNotifications('investor');
  }, [loadWatchlist, loadNotifications]);

  return (
    <Tabs
      tabBar={(props) => (
        <TabBar
          {...props}
          glyphs={GLYPHS}
          // Server notifications are not live — do not show unread badges yet.
          badges={{ alerts: 0 }}
        />
      )}
      screenOptions={{ headerShown: false, sceneStyle: { backgroundColor: colors.ground } }}>
      <Tabs.Screen name="index" options={{ title: 'Dealflow' }} />
      <Tabs.Screen name="watchlist" options={{ title: 'Watchlist' }} />
      <Tabs.Screen name="alerts" options={{ title: 'Alerts' }} />
      <Tabs.Screen name="profile" options={{ title: 'Profile' }} />
    </Tabs>
  );
}
