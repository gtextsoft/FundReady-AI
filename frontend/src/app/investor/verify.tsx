import { Pressable, ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Unavailable } from '@/components/unavailable';
import { Mono, Txt } from '@/components/ui/text';
import { ApiFailure } from '@/api';

/**
 * Investor identity verification is not live yet (Stripe Identity).
 * Do not collect credentials that cannot be submitted.
 */
export default function VerifyInvestor() {
  const insets = useSafeAreaInsets();

  return (
    <View className="flex-1 bg-ground">
      <View className="border-b border-line-soft px-[18px] pb-3" style={{ paddingTop: insets.top + 4 }}>
        <View className="h-[34px] flex-row items-center justify-between">
          <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={10}>
            <Txt className="text-[19px] text-ink">←</Txt>
          </Pressable>
          <Mono className="text-[10px] text-ink-faint" style={{ letterSpacing: 1.2 }}>
            INVESTOR VERIFICATION
          </Mono>
          <View className="w-5" />
        </View>
      </View>

      <ScrollView className="flex-1" contentContainerStyle={{ padding: 18, paddingTop: 20 }}>
        <Unavailable
          title="Verification coming soon"
          error={
            new ApiFailure(
              'not_implemented',
              'You can browse dealflow and express interest after confirming your email. Identity verification will open here when it is live.',
            )
          }
        />
      </ScrollView>
    </View>
  );
}
