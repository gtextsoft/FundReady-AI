import { useEffect } from 'react';
import { View } from 'react-native';
import { Redirect } from 'expo-router';

import { homeFor, SIGN_IN } from '@/lib/routes';
import { useSession } from '@/store/session';
import type { Role } from '@/api';

/**
 * Hard separation between the two sides of the marketplace.
 *
 * The role is fixed on the account at sign-up, so this is not a preference —
 * a founder who somehow lands on an investor URL is sent home, and vice versa.
 * Mounted in each side's root layout, so it covers every nested route
 * including ones added later.
 */
export function RoleGuard({ allow, children }: { allow: Role; children: React.ReactNode }) {
  const status = useSession((s) => s.status);
  const role = useSession((s) => s.role);
  const refreshAccount = useSession((s) => s.refreshAccount);

  const permitted = status === 'signedIn' && role === allow;

  useEffect(() => {
    if (permitted) refreshAccount();
  }, [permitted, refreshAccount]);

  if (status === 'loading') return <View className="flex-1 bg-obsidian" />;
  if (status === 'signedOut') return <Redirect href={SIGN_IN} />;
  if (role !== allow) return <Redirect href={homeFor(role)} />;

  return <>{children}</>;
}
