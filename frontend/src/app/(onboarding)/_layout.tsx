import { View } from 'react-native';
import { Redirect, Stack } from 'expo-router';

import { INVESTOR_HOME, SIGN_IN } from '@/lib/routes';
import { useSession } from '@/store/session';
import { useThemeColors } from '@/theme/use-theme-colors';

/**
 * The founder assessment runs full-screen, outside the dashboard tabs.
 * Investors have no business here — they are bounced to their own side.
 */
export default function OnboardingLayout() {
  const status = useSession((s) => s.status);
  const role = useSession((s) => s.role);
  const colors = useThemeColors();

  if (status === 'loading') return <View className="flex-1 bg-ground" />;
  if (status === 'signedOut') return <Redirect href={SIGN_IN} />;
  if (role !== 'founder') return <Redirect href={INVESTOR_HOME} />;

  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: colors.ground },
        animation: 'fade',
      }}
    />
  );
}
