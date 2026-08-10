import { View } from 'react-native';
import { Button } from '@/components/ui/button';
import { FilterChip } from '@/components/ui/controls';
import { Sheet } from '@/components/ui/sheet';
import { TxtMed } from '@/components/ui/text';
import { SECTORS } from '@/domain/types';
import { FILTER_COUNTRIES, FILTER_STAGES } from '@/domain/discovery-format';
import { useInvestor } from '@/store/investor';

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
  const sector = useInvestor((s) => s.sector);
  const stage = useInvestor((s) => s.stage);
  const country = useInvestor((s) => s.country);
  const setSector = useInvestor((s) => s.setSector);
  const setStage = useInvestor((s) => s.setStage);
  const setCountry = useInvestor((s) => s.setCountry);
  const clearFilters = useInvestor((s) => s.clearFilters);

  return (
    <Sheet visible={visible} onClose={onClose} title="Filters" action={{ label: 'Clear all', onPress: clearFilters }}>
      <View className="gap-[22px]">
        <View className="gap-[10px]">
          <TxtMed className="text-[12.5px]">Sector</TxtMed>
          <View className="flex-row flex-wrap gap-[7px]">
            {SECTORS.map((s) => (
              <FilterChip
                key={s}
                label={s}
                selected={sector === s}
                onPress={() => setSector(sector === s ? null : s)}
              />
            ))}
          </View>
        </View>

        <View className="gap-[10px]">
          <TxtMed className="text-[12.5px]">Stage</TxtMed>
          <View className="flex-row flex-wrap gap-[7px]">
            {FILTER_STAGES.map((s) => (
              <FilterChip
                key={s.value}
                label={s.label}
                selected={stage === s.value}
                onPress={() => setStage(stage === s.value ? null : s.value)}
              />
            ))}
          </View>
        </View>

        <View className="gap-[10px]">
          <TxtMed className="text-[12.5px]">Country</TxtMed>
          <View className="flex-row flex-wrap gap-[7px]">
            {FILTER_COUNTRIES.map((c) => (
              <FilterChip
                key={c.value}
                label={c.label}
                selected={country === c.value}
                onPress={() => setCountry(country === c.value ? null : c.value)}
              />
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
