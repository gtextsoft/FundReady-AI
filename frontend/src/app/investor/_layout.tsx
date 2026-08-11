import { Stack } from 'expo-router';

import { RoleGuard } from '@/components/role-guard';
import { C } from '@/theme/tokens';

export default function InvestorLayout() {
  return (
    <RoleGuard allow="investor">
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: C.obsidian },
          animation: 'slide_from_right',
        }}>
        <Stack.Screen name="(tabs)" options={{ animation: 'fade' }} />
      </Stack>
    </RoleGuard>
  );
}
