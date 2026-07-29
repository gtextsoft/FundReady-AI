import Animated from 'react-native-reanimated';
import { LinearGradient } from 'expo-linear-gradient';
import { cssInterop } from 'nativewind';

/**
 * NativeWind only teaches core React Native components to understand
 * `className`. Anything else — Reanimated's animated components, third-party
 * views — drops the prop silently: no error, no styles, and a `flex-row`
 * container quietly lays out as a column. Register them here.
 *
 * Imported for its side effect from src/app/_layout.tsx.
 */
cssInterop(Animated.View, { className: 'style' });
cssInterop(Animated.Text, { className: 'style' });
cssInterop(Animated.ScrollView, { className: 'style' });
cssInterop(LinearGradient, { className: 'style' });

export {};
