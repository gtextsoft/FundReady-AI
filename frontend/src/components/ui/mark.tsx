import { View } from 'react-native';
import { C } from '@/theme/tokens';

/** The SACI FundMe checker mark — a light square with two knocked-out quadrants. */
export function Mark({ size = 22, color = C.ink, ground = C.ground }: {
  size?: number;
  color?: string;
  ground?: string;
}) {
  const q = size / 2;
  return (
    <View style={{ width: size, height: size, backgroundColor: color }}>
      <View style={{ position: 'absolute', left: 0, top: 0, width: q, height: q, backgroundColor: ground }} />
      <View style={{ position: 'absolute', right: 0, bottom: 0, width: q, height: q, backgroundColor: ground }} />
    </View>
  );
}
