import { View } from 'react-native';
import { useThemeColors } from '@/theme/use-theme-colors';

/** The FundReady AI checker mark — a square with two knocked-out quadrants. */
export function Mark({
  size = 22,
  color,
  ground,
}: {
  size?: number;
  color?: string;
  ground?: string;
}) {
  const colors = useThemeColors();
  const ink = color ?? colors.ink;
  const bg = ground ?? colors.ground;
  const q = size / 2;
  return (
    <View style={{ width: size, height: size, backgroundColor: ink }}>
      <View style={{ position: 'absolute', left: 0, top: 0, width: q, height: q, backgroundColor: bg }} />
      <View style={{ position: 'absolute', right: 0, bottom: 0, width: q, height: q, backgroundColor: bg }} />
    </View>
  );
}
