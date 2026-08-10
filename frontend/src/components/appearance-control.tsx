import { View } from 'react-native';

import { Segmented } from '@/components/ui/controls';
import { Eyebrow, Txt } from '@/components/ui/text';
import { useAppearance, type AppearancePreference } from '@/store/appearance';

const OPTIONS: { value: AppearancePreference; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
];

/** Shared Appearance control for founder and investor profile screens. */
export function AppearanceControl() {
  const preference = useAppearance((s) => s.preference);
  const setPreference = useAppearance((s) => s.setPreference);

  return (
    <View className="gap-2">
      <Eyebrow>APPEARANCE</Eyebrow>
      <Txt className="text-[12.5px] text-ink-dim" style={{ lineHeight: 18 }}>
        Choose light, dark, or match your device.
      </Txt>
      <Segmented
        options={OPTIONS}
        value={preference}
        onChange={(v) => void setPreference(v)}
        grow
        size="md"
      />
    </View>
  );
}
