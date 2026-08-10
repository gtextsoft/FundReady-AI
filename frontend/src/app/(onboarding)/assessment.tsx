import { useEffect, useRef, useState } from 'react';
import { useWindowDimensions, View } from 'react-native';
import { router } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import Svg, { Defs, RadialGradient, Rect, Stop } from 'react-native-svg';
import Animated, {
  Easing,
  FadeIn,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';

import { Mark } from '@/components/ui/mark';
import { Mono, Txt, TxtMed } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { FOUNDER_HOME, route } from '@/lib/routes';
import { useBackTo } from '@/lib/use-back-to';
import { useFounder } from '@/store/founder';

const PHASES = [
  'Analysing market size and growth potential…',
  'Evaluating unit economics against global VC & PE benchmarks…',
  'Calculating your proprietary Fundability Score…',
  'Matching you with optimal growth pathways…',
];

const PHASE_MS = 1250;
const SETTLE_MS = 900;

export default function AssessmentScreen() {
  const { height } = useWindowDimensions();
  const [phase, setPhase] = useState(0);
  const company = useFounder((s) => s.profile.company);
  const runAudit = useFounder((s) => s.runAudit);
  const submitted = useRef(false);

  // The answers are already on their way to the server. Back means dashboard,
  // not back into the form they came from.
  useBackTo(FOUNDER_HOME);

  // Start the real audit while the phases play out. It takes minutes, not the
  // ~6 seconds this animation runs for, so the results screen picks up
  // whatever state the run is in — it does not wait here.
  useEffect(() => {
    if (submitted.current) return;
    submitted.current = true;
    // Failures are recorded on the store as `auditError` and rendered by the
    // results screen. Nothing is thrown away here.
    void runAudit();
  }, [runAudit]);

  useEffect(() => {
    const id = setInterval(() => {
      setPhase((p) => {
        if (p >= PHASES.length - 1) {
          clearInterval(id);
          setTimeout(() => router.replace(route('/results')), SETTLE_MS);
          return p;
        }
        return p + 1;
      });
    }, PHASE_MS);
    return () => clearInterval(id);
  }, []);

  return (
    <View className="flex-1 items-center justify-center overflow-hidden bg-ground px-8">
      {/* blue glow behind the mark */}
      <View className="absolute inset-0" pointerEvents="none">
        <Svg width="100%" height="100%">
          <Defs>
            <RadialGradient id="glow" cx="50%" cy="42%" r="55%">
              <Stop offset="0" stopColor={C.blue} stopOpacity={0.13} />
              <Stop offset="1" stopColor={C.blue} stopOpacity={0} />
            </RadialGradient>
          </Defs>
          <Rect x="0" y="0" width="100%" height="100%" fill="url(#glow)" />
        </Svg>
      </View>

      <ScanLine height={height} />

      <View className="mb-11 h-[168px] w-[168px] items-center justify-center">
        <PulseRing inset={0} delay={0} />
        <PulseRing inset={26} delay={400} />
        <Spinner />
        <Mark size={52} />
      </View>

      <Mono className="mb-[14px] text-[10px] text-ink-faint" style={{ letterSpacing: 1.5 }}>
        ASSESSING {(company || 'your company').toUpperCase()}
      </Mono>

      <View className="min-h-[52px] items-center justify-start">
        <Animated.View key={phase} entering={FadeIn.duration(400)}>
          <TxtMed className="text-center text-[17px]" style={{ letterSpacing: -0.3, lineHeight: 24 }}>
            {PHASES[phase]}
          </TxtMed>
        </Animated.View>
      </View>

      <View className="mt-[26px] flex-row gap-[6px]">
        {PHASES.map((_, i) => (
          <View
            key={i}
            className="h-[2px] w-[26px] rounded-[2px]"
            style={{ backgroundColor: phase >= i ? C.ink : C.lineStrong }}
          />
        ))}
      </View>

      <Txt className="absolute bottom-11 left-8 right-8 text-center text-[11px] text-ink-faint" style={{ lineHeight: 17 }}>
        Your figures are encrypted at rest and never shown to an investor until you approve a specific introduction.
      </Txt>
    </View>
  );
}

/** Concentric rings that breathe in and out, the second half a beat behind. */
function PulseRing({ inset, delay }: { inset: number; delay: number }) {
  const t = useSharedValue(0);

  useEffect(() => {
    t.value = withDelay(
      delay,
      withRepeat(
        withSequence(
          withTiming(1, { duration: 1300, easing: Easing.inOut(Easing.ease) }),
          withTiming(0, { duration: 1300, easing: Easing.inOut(Easing.ease) }),
        ),
        -1,
        false,
      ),
    );
  }, [t, delay]);

  const style = useAnimatedStyle(() => ({
    transform: [{ scale: 1 + t.value * 0.28 }],
    opacity: 0.35 + t.value * 0.55,
  }));

  return (
    <Animated.View
      pointerEvents="none"
      className="absolute rounded-full"
      style={[
        {
          top: inset,
          left: inset,
          right: inset,
          bottom: inset,
          borderWidth: 1,
          borderColor: inset ? 'rgba(237,237,237,0.22)' : 'rgba(237,237,237,0.14)',
        },
        style,
      ]}
    />
  );
}

/** Single-arc spinner — a circle whose top border alone is visible. */
function Spinner() {
  const spin = useSharedValue(0);

  useEffect(() => {
    spin.value = withRepeat(withTiming(1, { duration: 1500, easing: Easing.linear }), -1, false);
  }, [spin]);

  const style = useAnimatedStyle(() => ({ transform: [{ rotate: `${spin.value * 360}deg` }] }));

  return (
    <Animated.View
      pointerEvents="none"
      className="absolute inset-0 rounded-full"
      style={[{ borderWidth: 1.5, borderColor: 'transparent', borderTopColor: C.ink }, style]}
    />
  );
}

/** Slow scan sweep across the whole screen. */
function ScanLine({ height }: { height: number }) {
  const y = useSharedValue(-70);

  useEffect(() => {
    y.value = withRepeat(withTiming(height, { duration: 3400, easing: Easing.linear }), -1, false);
  }, [y, height]);

  const style = useAnimatedStyle(() => ({ transform: [{ translateY: y.value }] }));

  return (
    <Animated.View pointerEvents="none" className="absolute left-0 right-0 top-0 h-[70px]" style={style}>
      <LinearGradient colors={['transparent', 'rgba(0,112,243,0.09)', 'transparent']} style={{ flex: 1 }} />
    </Animated.View>
  );
}
