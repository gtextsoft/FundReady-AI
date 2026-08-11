import Svg, { Circle, Path } from 'react-native-svg';
import { C } from '@/theme/tokens';

/**
 * The FundReady mark — an F whose crossbar breaks into a rising signal,
 * terminating in the node where the AI reads.
 *
 * Two objects only: the letter and the signal. **Never recolour the F green**,
 * and never add a gradient, outline or rotation. The geometry is lifted
 * verbatim from the brand pack (`svg/mark-signal-on-dark.svg`) — keep the
 * 88×88 viewBox or the paths stop lining up.
 */
export function Mark({
  size = 22,
  color = C.bone,
  signal = C.signal,
}: {
  size?: number;
  color?: string;
  signal?: string;
}) {
  // The brand's small variant: at or below 24px the node is dropped and the
  // strokes thicken, because at that size the node closes up against the
  // signal stroke and the mark reads as a blob.
  const small = size <= 24;
  const stem = small ? 12 : 10;
  const rise = small ? 9 : 7;

  return (
    <Svg width={size} height={size} viewBox="0 0 88 88" fill="none">
      <Path d="M16 78V22a6 6 0 0 1 6-6h32" stroke={color} strokeWidth={stem} strokeLinecap="square" />
      <Path d="M16 47h26" stroke={color} strokeWidth={stem} strokeLinecap="square" />
      <Path
        d="M56 47l10-10 12 12"
        stroke={signal}
        strokeWidth={rise}
        strokeLinecap="square"
        strokeLinejoin="miter"
      />
      {small ? null : <Circle cx={78} cy={49} r={6} fill={signal} />}
    </Svg>
  );
}
