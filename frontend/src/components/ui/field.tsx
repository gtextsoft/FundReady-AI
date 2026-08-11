import { useState } from 'react';
import { Pressable, TextInput, View, type TextInputProps } from 'react-native';
import { FieldLabel, Txt } from './text';
import { C, Font } from '@/theme/tokens';

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
 */
export function Field({ label, prefix, suffix, mono, hint, style, ...rest }: FieldProps) {
  const [focused, setFocused] = useState(false);
  return (
    <View className="gap-[7px]">
      {label ? <FieldLabel>{label}</FieldLabel> : null}
      <View
        className="h-[46px] flex-row items-center gap-2 rounded-[9px] bg-carbon-low px-[14px]"
        style={{ borderWidth: 1, borderColor: focused ? C.boneFaint : C.graphiteStrong }}>
        {prefix ? <Txt className="text-[15px] text-bone-faint">{prefix}</Txt> : null}
        <TextInput
          className="min-w-0 flex-1 text-[15px] text-bone"
          placeholderTextColor={C.boneFaint}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          style={[{ fontFamily: mono ? Font.mono : Font.regular, padding: 0 }, style]}
          {...rest}
        />
        {suffix ? <Txt className="text-[13px] text-bone-faint">{suffix}</Txt> : null}
      </View>
      {hint ? <Txt className="text-[11px] text-bone-faint">{hint}</Txt> : null}
    </View>
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
            className="h-[44px] items-center justify-center rounded-[9px] border border-graphite-strong bg-carbon-low"
            style={{ width: `${100 / columns}%`, flexGrow: 1, flexBasis: 0, minWidth: 120 }}>
            {on ? (
              <View
                className="absolute inset-0 rounded-[9px]"
                style={{ borderWidth: 1.5, borderColor: C.bone, backgroundColor: 'rgba(237,240,234,0.09)' }}
              />
            ) : null}
            <Txt className="text-[13.5px] text-bone">{opt}</Txt>
          </Pressable>
        );
      })}
    </View>
  );
}
