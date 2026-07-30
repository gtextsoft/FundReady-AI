import { View } from 'react-native';
import { Button } from '@/components/ui/button';
import { FilterChip, Segmented } from '@/components/ui/controls';
import { Sheet } from '@/components/ui/sheet';
import { Slider } from '@/components/ui/slider';
import { Mono, TxtMed } from '@/components/ui/text';
import { SECTORS, STAGES, type MatchType } from '@/domain/types';
import { useInvestor } from '@/store/investor';

const MATCHES = [
  { value: 'All' as const, label: 'All' },
  { value: 'VC' as MatchType, label: 'VC-focused' },
  { value: 'PE' as MatchType, label: 'PE-focused' },
];

export function FilterSheet({
  visible,
  onClose,
  resultCount,
}: {
  visible: boolean;
  onClose: () => void;
  /** Drives the apply button copy — "Show 7 companies". */
  resultCount: number;
}) {
  const minScore = useInvestor((s) => s.minScore);
  const match = useInvestor((s) => s.match);
  const sectors = useInvestor((s) => s.sectors);
  const stages = useInvestor((s) => s.stages);
  const setMinScore = useInvestor((s) => s.setMinScore);
  const setMatch = useInvestor((s) => s.setMatch);
  const toggleSector = useInvestor((s) => s.toggleSector);
  const toggleStage = useInvestor((s) => s.toggleStage);
  const clearFilters = useInvestor((s) => s.clearFilters);

  return (
    <Sheet visible={visible} onClose={onClose} title="Filters" action={{ label: 'Clear all', onPress: clearFilters }}>
      <View className="gap-[22px]">
        <View className="gap-[10px]">
          <View className="flex-row items-center justify-between">
            <TxtMed className="text-[12.5px]">Fundability score</TxtMed>
            <Mono className="text-[12px] text-ink-muted">{minScore}–100</Mono>
          </View>
          <Slider value={minScore} onChange={setMinScore} label="Minimum fundability score" />
        </View>

        <View className="gap-[10px]">
          <TxtMed className="text-[12.5px]">Match type</TxtMed>
          <Segmented options={MATCHES} value={match} onChange={setMatch} grow size="md" />
        </View>

        <View className="gap-[10px]">
          <TxtMed className="text-[12.5px]">Sector</TxtMed>
          <View className="flex-row flex-wrap gap-[7px]">
            {SECTORS.map((s) => (
              <FilterChip key={s} label={s} selected={sectors.includes(s)} onPress={() => toggleSector(s)} />
            ))}
          </View>
        </View>

        <View className="gap-[10px]">
          <TxtMed className="text-[12.5px]">Stage</TxtMed>
          <View className="flex-row flex-wrap gap-[7px]">
            {STAGES.map((s) => (
              <FilterChip key={s} label={s} selected={stages.includes(s)} onPress={() => toggleStage(s)} />
            ))}
          </View>
        </View>

        <Button
          label={resultCount === 1 ? 'Show 1 company' : `Show ${resultCount} companies`}
          onPress={onClose}
        />
      </View>
    </Sheet>
  );
}
