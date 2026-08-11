import { useCallback, useMemo, useRef, useState } from 'react';
import { PanResponder, View } from 'react-native';
import { C } from '@/theme/tokens';

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));

/**
 * Minimum-score slider for the filter sheet.
 *
 * Built on the RN responder system rather than a native slider package: it
 * behaves identically on iOS, Android and the web preview, and adds no
 * dependency that Expo Go would have to carry.
 */
export function Slider({
  value,
  min = 0,
  max = 95,
  step = 5,
  onChange,
  label,
}: {
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (v: number) => void;
  label?: string;
}) {
  const [width, setWidth] = useState(0);
  const widthRef = useRef(0);
  const pageXRef = useRef(0);
  const viewRef = useRef<View>(null);

  const emit = useCallback(
    (x: number) => {
      if (!widthRef.current) return;
      const ratio = clamp(x / widthRef.current, 0, 1);
      const snapped = Math.round((min + ratio * (max - min)) / step) * step;
      onChange(clamp(snapped, min, max));
    },
    [min, max, step, onChange],
  );

  // The rule fires because `PanResponder.create` is handed callbacks that read
  // `pageXRef.current`. They are gesture handlers — they only ever run after
  // the gesture starts, never during render, which is the case the rule exists
  // to catch. Reading the ref at build time instead would freeze the layout
  // position at first mount and break the slider on rotation.
  const responder = useMemo(
    () =>
      // eslint-disable-next-line react-hooks/refs
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onPanResponderGrant: (e) => emit(e.nativeEvent.locationX),
        onPanResponderMove: (_, gesture) => emit(gesture.moveX - pageXRef.current),
      }),
    [emit],
  );

  const pct = max > min ? (value - min) / (max - min) : 0;
  const thumbX = Math.max(0, width * pct - 11);

  return (
    <View
      ref={viewRef}
      accessibilityRole="adjustable"
      accessibilityLabel={label ?? 'Minimum score'}
      accessibilityValue={{ min, max, now: value }}
      className="h-[26px] justify-center"
      onLayout={(e) => {
        const w = e.nativeEvent.layout.width;
        widthRef.current = w;
        setWidth(w);
        viewRef.current?.measureInWindow((x) => {
          pageXRef.current = x;
        });
      }}
      {...responder.panHandlers}>
      <View className="h-[3px] w-full rounded-[3px]" style={{ backgroundColor: C.graphiteStrong }}>
        <View className="h-full rounded-[3px]" style={{ width: `${pct * 100}%`, backgroundColor: C.bone }} />
      </View>
      <View
        pointerEvents="none"
        className="absolute h-[22px] w-[22px] rounded-full"
        style={{ left: thumbX, backgroundColor: C.bone, borderWidth: 3, borderColor: C.obsidian }}
      />
    </View>
  );
}
