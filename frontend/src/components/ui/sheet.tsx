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
            style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
          />
        </Animated.View>

        <Animated.View
          entering={SlideInDown.duration(240)}
          className="max-h-[82%] rounded-t-[18px] border-t border-line-strong bg-surface-1 px-5 pt-3"
          style={{ paddingBottom: insets.bottom + 30 }}>
          <View className="mx-auto mb-4 h-1 w-9 rounded-[4px] bg-line-dash" />
          <View className="mb-5 flex-row items-center justify-between">
            <TxtSemi className="text-[16px]" style={{ letterSpacing: -0.3 }}>
              {title}
            </TxtSemi>
            {action ? (
              <Pressable accessibilityRole="button" onPress={action.onPress} hitSlop={8}>
                <Txt className="text-[12px] text-ink-dim">{action.label}</Txt>
              </Pressable>
            ) : null}
          </View>
          <ScrollView showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
            {children}
          </ScrollView>
        </Animated.View>
      </View>
    </Modal>
  );
}
