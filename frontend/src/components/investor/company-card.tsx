import { Pressable, View } from 'react-native';
import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
import {
  stageLabel,
  verdictColor,
  verdictLabel,
  verdictScoreText,
} from '@/domain/discovery-format';
import type { DiscoveredStartup } from '@/domain/discovery';
import { initials } from '@/lib/format';

/**
 * Summary-tier dealflow row.
 *
 * Deliberately thin: name, market, two verdicts. No MRR / growth / match —
 * those are full-report fields and only land after a FundReady AI reveal.
 */
export function CompanyCard({
  startup,
  watched,
  onPress,
  onToggleWatch,
}: {
  startup: DiscoveredStartup;
  watched: boolean;
  onPress: () => void;
  onToggleWatch: () => void;
}) {
  const name = startup.name?.trim() || 'Unnamed startup';
  const fundColor = verdictColor(startup.fundability.level);

  return (
    <View className="relative">
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${name}, fundability ${verdictLabel(startup.fundability.level)}`}
        onPress={onPress}
        className="rounded-[12px] border border-line bg-surface-1 p-[14px]">
        <View className="flex-row items-start gap-[11px]">
          <View className="h-[34px] w-[34px] items-center justify-center rounded-[9px] border border-line-strong bg-surface-3">
            <TxtSemi className="text-[11px] text-ink-muted">{initials(name)}</TxtSemi>
          </View>

          <View className="min-w-0 flex-1">
            <TxtSemi className="text-[14.5px]" style={{ letterSpacing: -0.2 }} numberOfLines={1}>
              {name}
            </TxtSemi>
            <Txt className="mt-[3px] text-[12px] text-ink-dim" numberOfLines={1}>
              {[startup.sector, stageLabel(startup.stage), startup.country]
                .filter(Boolean)
                .join(' · ') || 'Market undisclosed'}
            </Txt>
          </View>

          <View className="items-end gap-[5px]">
            <View
              className="min-w-[44px] items-center rounded-[8px] px-2 py-[5px]"
              style={{
                backgroundColor: `${fundColor}1a`,
                borderWidth: 1,
                borderColor: `${fundColor}4d`,
              }}>
              <Mono className="text-[14px]" style={{ color: fundColor }}>
                {verdictScoreText(startup.fundability)}
              </Mono>
            </View>
            <View className="h-[20px] w-[22px]" />
          </View>
        </View>

        <View className="mt-3 flex-row border-t pt-[10px]" style={{ borderTopColor: '#171717' }}>
          <VerdictMetric
            label="FUNDABILITY"
            level={startup.fundability.level}
            score={verdictScoreText(startup.fundability)}
          />
          <VerdictMetric
            label="SALEABILITY"
            level={startup.saleability.level}
            score={verdictScoreText(startup.saleability)}
          />
        </View>
      </Pressable>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel={watched ? 'Remove from watchlist' : 'Add to watchlist'}
        hitSlop={10}
        onPress={onToggleWatch}
        className="absolute right-[13px] top-[43px] h-[20px] w-[24px] items-center justify-center">
        <Txt className="text-[15px]" style={{ color: watched ? C.amb : '#3d3d3d' }}>
          {watched ? '★' : '☆'}
        </Txt>
      </Pressable>
    </View>
  );
}

function VerdictMetric({
  label,
  level,
  score,
}: {
  label: string;
  level: string;
  score: string;
}) {
  const color = verdictColor(level);
  return (
    <View className="flex-1">
      <Txt className="text-[9.5px] text-ink-faint" style={{ letterSpacing: 0.5 }}>
        {label}
      </Txt>
      <View className="mt-[2px] flex-row items-baseline gap-[6px]">
        <Mono className="text-[12.5px]" style={{ color }}>
          {score}
        </Mono>
        <Txt className="text-[11px] text-ink-muted" numberOfLines={1}>
          {verdictLabel(level)}
        </Txt>
      </View>
    </View>
  );
}
