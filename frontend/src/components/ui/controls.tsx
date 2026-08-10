import { Pressable, View } from 'react-native';
import { Mono, Txt, TxtMed } from './text';
import { useThemeColors } from '@/theme/use-theme-colors';

/**
 * Segmented control — MRR/ARR, All/VC/PE, Metrics/AI memo. `grow` makes the
 * options share the width evenly; without it they hug their labels.
 */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  grow = false,
  size = 'sm',
}: {
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  grow?: boolean;
  size?: 'sm' | 'md';
}) {
  const colors = useThemeColors();
  return (
    <View className="flex-row gap-[2px] rounded-[9px] border border-line bg-surface-1 p-[3px]">
      {options.map((opt) => {
        const on = opt.value === value;
        return (
          <Pressable
            key={opt.value}
            accessibilityRole="button"
            accessibilityState={{ selected: on }}
            onPress={() => onChange(opt.value)}
            className={`items-center justify-center rounded-[5px] ${grow ? 'flex-1' : ''} ${
              size === 'md' ? 'px-[11px] py-2' : 'px-[11px] py-[5px]'
            }`}
            style={{ backgroundColor: on ? colors.ink : 'transparent' }}>
            <TxtMed className={`${size === 'md' ? 'text-[12.5px]' : 'text-[11.5px]'} ${on ? 'text-ground' : 'text-ink-muted'}`}>
              {opt.label}
            </TxtMed>
          </Pressable>
        );
      })}
    </View>
  );
}

/** Filter/sort chip. Selection is an inset overlay so the chip never reflows. */
export function Chip({
  label,
  selected,
  onPress,
  badge,
  leading,
}: {
  label: string;
  selected?: boolean;
  onPress: () => void;
  /** Small pill on the right, used for the active-filter count. */
  badge?: number;
  leading?: string;
}) {
  const colors = useThemeColors();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: !!selected }}
      onPress={onPress}
      className="h-[30px] flex-row items-center gap-[6px] rounded-[8px] border border-line-strong bg-surface-1 px-[11px]">
      {selected ? (
        <View
          className="absolute inset-0 rounded-[8px]"
          style={{ borderWidth: 1.5, borderColor: colors.ink, backgroundColor: 'rgba(128,128,128,0.12)' }}
        />
      ) : null}
      {leading ? <Txt className="text-[12px] text-ink">{leading}</Txt> : null}
      <Txt className="text-[12px] text-ink">{label}</Txt>
      {badge ? (
        <View className="h-[15px] min-w-[15px] items-center justify-center rounded-[8px] bg-ink px-[3px]">
          <Mono className="text-[9px] text-ground">{badge}</Mono>
        </View>
      ) : null}
    </Pressable>
  );
}

/** Larger chip used inside the filter sheet for sectors and stages. */
export function FilterChip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  const colors = useThemeColors();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      className="rounded-[8px] border border-line-strong bg-ground px-3 py-2">
      {selected ? (
        <View
          className="absolute inset-0 rounded-[8px]"
          style={{ borderWidth: 1.5, borderColor: colors.ink, backgroundColor: 'rgba(128,128,128,0.12)' }}
        />
      ) : null}
      <Txt className="text-[12.5px] text-ink">{label}</Txt>
    </Pressable>
  );
}

/** Bordered meta pill — stage, location, sector on the deep dive. */
export function MetaPill({ label }: { label: string }) {
  return (
    <View className="rounded-[5px] border border-line-strong px-2 py-[3px]">
      <Mono className="text-[10px] text-ink-muted">{label}</Mono>
    </View>
  );
}

export function Divider({ className }: { className?: string }) {
  return <View className={`h-[1px] bg-surface-4 ${className ?? ''}`} />;
}
