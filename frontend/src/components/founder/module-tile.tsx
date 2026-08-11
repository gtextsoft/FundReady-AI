import { Pressable, View } from 'react-native';
import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import { lockLabel, type Gate } from '@/domain/access';

/**
 * One entry on the founder dashboard.
 *
 * A locked tile is never hidden — it stays visible and legible, states the
 * reason it is locked, and routes to whatever would unlock it. Hiding gated
 * features just makes the product look empty.
 */
export function ModuleTile({
  glyph,
  title,
  subtitle,
  gate,
  onPress,
  badge,
}: {
  glyph: string;
  title: string;
  subtitle: string;
  gate: Gate;
  onPress: () => void;
  /** Small count pill, e.g. pending investor requests. */
  badge?: number;
}) {
  const locked = !gate.allowed;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={locked ? `${title}, locked` : title}
      accessibilityState={{ disabled: false }}
      onPress={onPress}
      className="flex-1 rounded-[12px] border border-graphite bg-carbon-low p-[14px]"
      style={{ minWidth: 150 }}>
      <View className="mb-[10px] flex-row items-start justify-between">
        <Txt className="text-[17px]" style={{ color: locked ? C.boneFaint : C.bone }}>
          {glyph}
        </Txt>

        {locked ? (
          <View className="rounded-[4px] border border-graphite-strong px-[6px] py-[2px]">
            <Mono className="text-[8.5px]" style={{ letterSpacing: 0.6, color: C.boneFaint }}>
              {gate.reason === 'payment' ? 'LOCKED' : 'VERIFY'}
            </Mono>
          </View>
        ) : badge ? (
          <View
            className="h-[18px] min-w-[18px] items-center justify-center rounded-full px-[5px]"
            style={{ backgroundColor: C.flag }}>
            <Mono className="text-[9px] text-obsidian">{badge}</Mono>
          </View>
        ) : null}
      </View>

      <TxtSemi className="text-[13.5px]" style={{ color: locked ? C.boneSecondary : C.bone }}>
        {title}
      </TxtSemi>
      <Txt className="mt-[3px] text-[11.5px] text-bone-muted" style={{ lineHeight: 17 }}>
        {locked ? lockLabel(gate.reason) : subtitle}
      </Txt>
    </Pressable>
  );
}
