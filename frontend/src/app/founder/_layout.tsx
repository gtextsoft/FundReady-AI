import { Stack } from 'expo-router';

import { RoleGuard } from '@/components/role-guard';
import { useThemeColors } from '@/theme/use-theme-colors';

/**
 * Founder side. The tab group is one screen inside this stack, so verification,
 * the paywall and the AI mentor push over the tabs full-screen.
 */
export default function FounderLayout() {
  const colors = useThemeColors();
  return (
    <RoleGuard allow="founder">
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: colors.ground },
          animation: 'slide_from_right',
        }}>
        <Stack.Screen name="(tabs)" options={{ animation: 'fade' }} />
      </Stack>
    </RoleGuard>
  );
}
