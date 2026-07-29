import { View } from 'react-native';
import { Redirect, Stack } from 'expo-router';

import { C } from '@/theme/tokens';
import { INVESTOR_HOME, SIGN_IN } from '@/lib/routes';
import { useSession } from '@/store/session';

/**
 * The founder assessment runs full-screen, outside the dashboard tabs.
 * Investors have no business here — they are bounced to their own side.
 */
export default function OnboardingLayout() {
  const status = useSession((s) => s.status);
  const role = useSession((s) => s.role);

  if (status === 'loading') return <View className="flex-1 bg-ground" />;
  if (status === 'signedOut') return <Redirect href={SIGN_IN} />;
  if (role !== 'founder') return <Redirect href={INVESTOR_HOME} />;

  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: C.ground },
        animation: 'fade',
      }}
    />
  );
}
