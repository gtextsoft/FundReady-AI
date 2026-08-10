import { Stack } from 'expo-router';

import { RoleGuard } from '@/components/role-guard';
import { useThemeColors } from '@/theme/use-theme-colors';

export default function InvestorLayout() {
  const colors = useThemeColors();
  return (
    <RoleGuard allow="investor">
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
