import { useEffect, useState } from 'react';
import { Animated, Easing, View } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { Mono, Txt } from './text';

const AnimatedCircle = Animated.createAnimatedComponent(Circle);

const SIZE = 172;
const R = 70;
const CIRCUMFERENCE = 2 * Math.PI * R; // 439.8

/**
 * The results ring: a track plus a progress arc that sweeps to the score.
 *
 * Uses the core Animated API rather than Reanimated — animating an SVG prop
 * needs `useNativeDriver: false` anyway, and this keeps the web preview
 * identical to native.
 */
export function ScoreRing({ score, color }: { score: number; color: string }) {
  // A lazy `useState` initialiser rather than `useRef(...).current`: both give
  // one stable Animated.Value, but reading `.current` during render is a real
  // hazard the linter is right to flag, and the ref form also constructs a
  // throwaway Value on every render.
  const [offset] = useState(() => new Animated.Value(CIRCUMFERENCE));

  useEffect(() => {
    Animated.timing(offset, {
      toValue: CIRCUMFERENCE * (1 - score / 100),
      duration: 1100,
      easing: Easing.bezier(0.2, 0.8, 0.2, 1),
      useNativeDriver: false,
    }).start();
  }, [score, offset]);

  return (
    <View style={{ width: SIZE, height: SIZE }}>
      <Svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} style={{ transform: [{ rotate: '-90deg' }] }}>
        <Circle cx={86} cy={86} r={R} fill="none" stroke="#1c1c1c" strokeWidth={10} />
        <AnimatedCircle
          cx={86}
          cy={86}
          r={R}
          fill="none"
          stroke={color}
          strokeWidth={10}
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={offset}
        />
      </Svg>
      <View className="absolute inset-0 items-center justify-center">
        <Mono className="text-[52px] text-ink" style={{ letterSpacing: -2.5, lineHeight: 56 }}>
          {score}
        </Mono>
        <Txt className="mt-[2px] text-[11px] text-ink-faint">FUNDABILITY / 100</Txt>
      </View>
    </View>
  );
}

/** Compact score chip used on dealflow cards. */
export function ScoreBadge({ score, color, bg, border }: { score: number; color: string; bg: string; border: string }) {
  return (
    <View className="rounded-[6px] px-2 py-[3px]" style={{ backgroundColor: bg, borderWidth: 1, borderColor: border }}>
      <Mono className="text-[13px]" style={{ color }}>
        {score}
      </Mono>
    </View>
  );
}
