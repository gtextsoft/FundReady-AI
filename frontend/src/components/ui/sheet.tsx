import { Modal, Pressable, ScrollView, View } from 'react-native';
import Animated, { FadeIn, FadeOut, SlideInDown } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { TxtSemi, Txt } from './text';

/**
 * Bottom sheet: dimmed backdrop that closes on tap, plus a rounded panel that
 * rises from the bottom edge and is capped at 82% of the screen.
 */
export function Sheet({
  visible,
  onClose,
  title,
  action,
  children,
}: {
  visible: boolean;
  onClose: () => void;
  title: string;
  /** Right-aligned text button in the header, e.g. "Clear all". */
  action?: { label: string; onPress: () => void };
  children: React.ReactNode;
}) {
  const insets = useSafeAreaInsets();
  return (
    <Modal visible={visible} transparent animationType="none" onRequestClose={onClose} statusBarTranslucent>
      <View className="flex-1 justify-end">
        <Animated.View entering={FadeIn.duration(180)} exiting={FadeOut.duration(140)} className="absolute inset-0">
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Close"
            onPress={onClose}
            className="flex-1"
            style={{ backgroundColor: 'rgba(12,15,14,0.6)' }}
          />
        </Animated.View>

        <Animated.View
          entering={SlideInDown.duration(240)}
          className="max-h-[82%] rounded-t-[18px] border-t border-graphite-strong bg-carbon-low px-5 pt-3"
          style={{ paddingBottom: insets.bottom + 30 }}>
          <View className="mx-auto mb-4 h-1 w-9 rounded-[4px] bg-graphite-bright" />
          <View className="mb-5 flex-row items-center justify-between">
            <TxtSemi className="text-[16px]" style={{ letterSpacing: -0.3 }}>
              {title}
            </TxtSemi>
            {action ? (
              <Pressable accessibilityRole="button" onPress={action.onPress} hitSlop={8}>
                <Txt className="text-[12px] text-bone-muted">{action.label}</Txt>
              </Pressable>
            ) : null}
          </View>
          {/* `shrink` is load-bearing. Without it the ScrollView takes its
              full content height and overflows the panel's `max-h-[82%]`
              instead of scrolling inside it. React Native does not clip by
              default, so the overflowing rows still *render* — below the
              sheet, outside its bounds, where taps never reach them. The
              symptom is the worst kind: a list that looks complete but whose
              last few entries silently do nothing. */}
          <ScrollView
            className="shrink"
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled">
            {children}
          </ScrollView>
        </Animated.View>
      </View>
    </Modal>
  );
}
