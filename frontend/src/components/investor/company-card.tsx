import { Pressable, View } from 'react-native';
import { ScoreBadge } from '@/components/ui/score-ring';
import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { C, scoreBorder, scoreColor, scoreTint } from '@/theme/tokens';
import { growthColor, growthLabel, initials, moneyShort } from '@/lib/format';
import type { CompanySummary } from '@/api';

/**
 * Dealflow row. The desktop table's eight columns collapse into a header block
 * plus a four-metric strip, keeping score and star in the same corner.
 */
export function CompanyCard({
  company,
  watched,
  onPress,
  onToggleWatch,
}: {
  company: CompanySummary;
  watched: boolean;
  onPress: () => void;
  onToggleWatch: () => void;
}) {
  return (
    // The star cannot live inside the card's Pressable: on web both render as
    // <button>, and a nested button is invalid HTML that React refuses to
    // hydrate. They are siblings, with the star positioned over the slot the
    // score column reserves for it.
    <View className="relative">
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${company.name}, fundability ${company.score}`}
        onPress={onPress}
        className="rounded-[12px] border border-graphite bg-carbon-low p-[14px]">
        <View className="flex-row items-start gap-[11px]">
          <View className="h-[34px] w-[34px] items-center justify-center rounded-[9px] border border-graphite-strong bg-carbon-high">
            <TxtSemi className="text-[11px] text-bone-secondary">{initials(company.name)}</TxtSemi>
          </View>

          <View className="min-w-0 flex-1">
            <View className="flex-row items-center gap-[7px]">
              <TxtSemi className="text-[14.5px]" style={{ letterSpacing: -0.2 }} numberOfLines={1}>
                {company.name}
              </TxtSemi>
              <View className="rounded-[4px] border border-graphite-strong px-[5px] py-[1px]">
                <Mono className="text-[9.5px] text-bone-secondary">{company.match}</Mono>
              </View>
            </View>
            <Txt className="mt-[3px] text-[12px] text-bone-muted" style={{ lineHeight: 17 }} numberOfLines={2}>
              {company.tagline}
            </Txt>
          </View>

          <View className="items-center gap-[5px]">
            <ScoreBadge
              score={company.score}
              color={scoreColor(company.score)}
              bg={scoreTint(company.score)}
              border={scoreBorder(company.score)}
            />
            {/* Reserves the star's slot so the metric strip sits at the same
                height as in the design; the real control is layered on top. */}
            <View className="h-[20px] w-[22px]" />
          </View>
        </View>

        <View className="mt-3 flex-row border-t pt-[10px]" style={{ borderTopColor: '#171717' }}>
          <Metric label="MRR" value={moneyShort(company.mrr)} mono />
          <Metric label="GROWTH" value={growthLabel(company.growth)} color={growthColor(company.growth)} mono />
          <Metric label="STAGE" value={company.stage} />
          <Metric label="SECTOR" value={company.sector} flex={1.2} />
        </View>
      </Pressable>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel={watched ? 'Remove from watchlist' : 'Add to watchlist'}
        hitSlop={10}
        onPress={onToggleWatch}
        className="absolute right-[13px] top-[43px] h-[20px] w-[24px] items-center justify-center">
        <Txt className="text-[15px]" style={{ color: watched ? C.flag : C.boneGhost }}>
          {watched ? '★' : '☆'}
        </Txt>
      </Pressable>
    </View>
  );
}

function Metric({
  label,
  value,
  color,
  mono,
  flex = 1,
}: {
  label: string;
  value: string;
  color?: string;
  mono?: boolean;
  flex?: number;
}) {
  return (
    <View style={{ flex }}>
      <Txt className="text-[9.5px] text-bone-faint" style={{ letterSpacing: 0.5 }}>
        {label}
      </Txt>
      {mono ? (
        <Mono className="mt-[2px] text-[12.5px]" style={color ? { color } : undefined}>
          {value}
        </Mono>
      ) : (
        <Txt className="mt-[2px] text-[12px] text-bone-secondary" numberOfLines={1}>
          {value}
        </Txt>
      )}
    </View>
  );
}
