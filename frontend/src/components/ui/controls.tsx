import { Pressable, View } from 'react-native';
import { Mono, Txt, TxtMed } from './text';
import { C } from '@/theme/tokens';

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
  return (
    <View className="flex-row gap-[2px] rounded-[9px] border border-graphite bg-carbon-low p-[3px]">
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
            style={{ backgroundColor: on ? C.bone : 'transparent' }}>
            <TxtMed className={`${size === 'md' ? 'text-[12.5px]' : 'text-[11.5px]'} ${on ? 'text-obsidian' : 'text-bone-secondary'}`}>
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
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: !!selected }}
      onPress={onPress}
      className="h-[30px] flex-row items-center gap-[6px] rounded-[8px] border border-graphite-strong bg-carbon-low px-[11px]">
      {selected ? (
        <View
          className="absolute inset-0 rounded-[8px]"
          style={{ borderWidth: 1.5, borderColor: C.bone, backgroundColor: 'rgba(237,240,234,0.10)' }}
        />
      ) : null}
      {leading ? <Txt className="text-[12px] text-bone">{leading}</Txt> : null}
      <Txt className="text-[12px] text-bone">{label}</Txt>
      {badge ? (
        <View className="h-[15px] min-w-[15px] items-center justify-center rounded-[8px] bg-bone px-[3px]">
          <Mono className="text-[9px] text-obsidian">{badge}</Mono>
        </View>
      ) : null}
    </Pressable>
  );
}

/** Larger chip used inside the filter sheet for sectors and stages. */
export function FilterChip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      className="rounded-[8px] border border-graphite-strong bg-obsidian px-3 py-2">
      {selected ? (
        <View
          className="absolute inset-0 rounded-[8px]"
          style={{ borderWidth: 1.5, borderColor: C.bone, backgroundColor: 'rgba(237,240,234,0.10)' }}
        />
      ) : null}
      <Txt className="text-[12.5px] text-bone">{label}</Txt>
    </Pressable>
  );
}

/** Bordered meta pill — stage, location, sector on the deep dive. */
export function MetaPill({ label }: { label: string }) {
  return (
    <View className="rounded-[5px] border border-graphite-strong px-2 py-[3px]">
      <Mono className="text-[10px] text-bone-secondary">{label}</Mono>
    </View>
  );
}

export function Divider({ className }: { className?: string }) {
  return <View className={`h-[1px] bg-carbon-top ${className ?? ''}`} />;
}
