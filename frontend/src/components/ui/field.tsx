import { useState } from 'react';
import { Pressable, TextInput, View, type TextInputProps } from 'react-native';
import Svg, { Circle, Path } from 'react-native-svg';
import { FieldLabel, Txt } from './text';
import { Font } from '@/theme/tokens';
import { useThemeColors } from '@/theme/use-theme-colors';

type FieldProps = TextInputProps & {
  /** Omit (or pass '') when the caller renders its own label row. */
  label?: string;
  /** Fixed text glued to the left inside the box, e.g. "$". */
  prefix?: string;
  /** Fixed text glued to the right inside the box, e.g. "% MoM" or "MRR". */
  suffix?: string;
  /** Monospace input — used for every numeric field in the design. */
  mono?: boolean;
  hint?: string;
};

/**
 * Labelled input. The box is a sibling of the label rather than a wrapper so
 * the focus border can live on the box alone, matching the prototype.
 *
 * When `secureTextEntry` is set, an eye control toggles password preview.
 */
export function Field({
  label,
  prefix,
  suffix,
  mono,
  hint,
  style,
  secureTextEntry,
  ...rest
}: FieldProps) {
  const colors = useThemeColors();
  const [focused, setFocused] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const isPassword = secureTextEntry === true;
  const hidden = isPassword && !revealed;

  return (
    <View className="gap-[7px]">
      {label ? <FieldLabel>{label}</FieldLabel> : null}
      <View
        className="h-[46px] flex-row items-center gap-2 rounded-[9px] bg-surface-1 px-[14px]"
        style={{ borderWidth: 1, borderColor: focused ? colors.inkFaint : colors.lineStrong }}>
        {prefix ? <Txt className="text-[15px] text-ink-faint">{prefix}</Txt> : null}
        <TextInput
          className="min-w-0 flex-1 text-[15px] text-ink"
          placeholderTextColor={colors.inkFaint}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          style={[{ fontFamily: mono ? Font.mono : Font.regular, padding: 0 }, style]}
          secureTextEntry={hidden}
          {...rest}
        />
        {suffix && !isPassword ? <Txt className="text-[13px] text-ink-faint">{suffix}</Txt> : null}
        {isPassword ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={revealed ? 'Hide password' : 'Show password'}
            hitSlop={10}
            onPress={() => setRevealed((v) => !v)}
            className="h-9 w-9 items-center justify-center">
            <EyeIcon open={revealed} color={colors.inkMuted} />
          </Pressable>
        ) : null}
      </View>
      {hint ? <Txt className="text-[11px] text-ink-faint">{hint}</Txt> : null}
    </View>
  );
}

function EyeIcon({ open, color }: { open: boolean; color: string }) {
  if (open) {
    // Eye with a slash — password is currently visible; tap to hide.
    return (
      <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
        <Path
          d="M3 3l18 18"
          stroke={color}
          strokeWidth={1.75}
          strokeLinecap="round"
        />
        <Path
          d="M10.6 10.6a2 2 0 002.8 2.8M6.7 6.8C4.7 8.1 3.3 9.9 2.5 12c1.5 4 5.2 6.8 9.5 6.8 1.7 0 3.3-.4 4.7-1.1M9.9 5.3A10.4 10.4 0 0112 5.2c4.3 0 8 2.8 9.5 6.8-.5 1.3-1.3 2.5-2.3 3.5"
          stroke={color}
          strokeWidth={1.75}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </Svg>
    );
  }

  return (
    <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
      <Path
        d="M2.5 12C4 8.2 7.7 5.4 12 5.4S20 8.2 21.5 12C20 15.8 16.3 18.6 12 18.6S4 15.8 2.5 12z"
        stroke={color}
        strokeWidth={1.75}
        strokeLinejoin="round"
      />
      <Circle cx={12} cy={12} r={2.6} stroke={color} strokeWidth={1.75} />
    </Svg>
  );
}

/**
 * Selectable tile grid — the stage picker and the Yes/No technical toggle.
 * Selection is drawn as an inset overlay so the tile does not shift by 0.5px
 * when the border thickens, exactly as the prototype does it.
 */
export function OptionGrid<T extends string>({
  options,
  value,
  onChange,
  columns = 2,
}: {
  options: readonly T[];
  value: string;
  onChange: (v: T) => void;
  columns?: number;
}) {
  const colors = useThemeColors();
  return (
    <View className="flex-row flex-wrap" style={{ gap: 8 }}>
      {options.map((opt) => {
        const on = value === opt;
        return (
          <Pressable
            key={opt}
            accessibilityRole="button"
            accessibilityState={{ selected: on }}
            onPress={() => onChange(opt)}
            className="h-[44px] items-center justify-center rounded-[9px] border border-line-strong bg-surface-1"
            style={{ width: `${100 / columns}%`, flexGrow: 1, flexBasis: 0, minWidth: 120 }}>
            {on ? (
              <View
                className="absolute inset-0 rounded-[9px]"
                style={{
                  borderWidth: 1.5,
                  borderColor: colors.ink,
                  backgroundColor: 'rgba(128,128,128,0.12)',
                }}
              />
            ) : null}
            <Txt className="text-[13.5px] text-ink">{opt}</Txt>
          </Pressable>
        );
      })}
    </View>
  );
}
