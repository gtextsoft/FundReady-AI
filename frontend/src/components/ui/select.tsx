import { useState } from 'react';
import { Keyboard, Pressable, View } from 'react-native';
import { FieldLabel, Txt, TxtMed } from './text';
import { Sheet } from './sheet';
import { C } from '@/theme/tokens';

/**
 * React Native has no <select>, so the picker is a field-shaped button that
 * opens a sheet of options. Keeps the same 46px box as <Field>.
 */
export function Select<T extends string>({
  label,
  value,
  placeholder,
  options,
  onChange,
}: {
  label: string;
  value: string;
  placeholder: string;
  options: readonly T[];
  onChange: (v: T) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <View className="gap-[7px]">
      <FieldLabel>{label}</FieldLabel>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={label}
        accessibilityValue={{ text: value || placeholder }}
        // The keyboard is usually up when this is tapped — the field above it
        // was just being typed into. Left open, it covers the bottom of the
        // sheet, so the options behind it cannot be reached however far the
        // list is scrolled.
        onPress={() => {
          Keyboard.dismiss();
          setOpen(true);
        }}
        className="h-[46px] flex-row items-center justify-between rounded-[9px] border border-graphite-strong bg-carbon-low px-[14px]">
        <Txt className={`text-[15px] ${value ? 'text-bone' : 'text-bone-faint'}`}>{value || placeholder}</Txt>
        <Txt className="text-[11px] text-bone-faint">▾</Txt>
      </Pressable>

      <Sheet visible={open} onClose={() => setOpen(false)} title={label}>
        <View className="gap-[1px] overflow-hidden rounded-[11px]" style={{ backgroundColor: C.carbonTop }}>
          {options.map((opt) => {
            const on = opt === value;
            return (
              <Pressable
                key={opt}
                accessibilityRole="button"
                accessibilityState={{ selected: on }}
                onPress={() => {
                  onChange(opt);
                  setOpen(false);
                }}
                className="flex-row items-center justify-between bg-carbon-low px-[14px] py-[14px]">
                {on ? (
                  <TxtMed className="text-[14px] text-bone">{opt}</TxtMed>
                ) : (
                  <Txt className="text-[14px] text-bone-secondary">{opt}</Txt>
                )}
                {on ? <Txt className="text-[13px] text-bone">✓</Txt> : null}
              </Pressable>
            );
          })}
        </View>
      </Sheet>
    </View>
  );
}
