import { useState } from 'react';
import { Pressable, View } from 'react-native';
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
        onPress={() => setOpen(true)}
        className="h-[46px] flex-row items-center justify-between rounded-[9px] border border-line-strong bg-surface-1 px-[14px]">
        <Txt className={`text-[15px] ${value ? 'text-ink' : 'text-ink-faint'}`}>{value || placeholder}</Txt>
        <Txt className="text-[11px] text-ink-faint">▾</Txt>
      </Pressable>

      <Sheet visible={open} onClose={() => setOpen(false)} title={label}>
        <View className="gap-[1px] overflow-hidden rounded-[11px]" style={{ backgroundColor: C.surface4 }}>
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
                className="flex-row items-center justify-between bg-surface-1 px-[14px] py-[14px]">
                {on ? (
                  <TxtMed className="text-[14px] text-ink">{opt}</TxtMed>
                ) : (
                  <Txt className="text-[14px] text-ink-muted">{opt}</Txt>
                )}
                {on ? <Txt className="text-[13px] text-ink">✓</Txt> : null}
              </Pressable>
            );
          })}
        </View>
      </Sheet>
    </View>
  );
}
