import { View } from 'react-native';
import { Redirect } from 'expo-router';

import { homeFor, SIGN_IN } from '@/lib/routes';
import { useSession } from '@/store/session';

/**
 * Entry gate. Holds a blank ground until the stored session has been read
 * back, then sends the user to their own side of the marketplace.
 */
export default function Index() {
  const status = useSession((s) => s.status);
  const role = useSession((s) => s.role);

  if (status === 'loading') return <View className="flex-1 bg-obsidian" />;
  if (status === 'signedOut') return <Redirect href={SIGN_IN} />;
  return <Redirect href={homeFor(role)} />;
}
