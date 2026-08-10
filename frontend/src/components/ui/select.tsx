import { useState } from 'react';
import { Keyboard, Pressable, View } from 'react-native';
import { FieldLabel, Txt, TxtMed } from './text';
import { Sheet } from './sheet';
import { useThemeColors } from '@/theme/use-theme-colors';

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
  hint,
}: {
  label: string;
  value: string;
  placeholder: string;
  options: readonly T[];
  onChange: (v: T) => void;
  hint?: string;
}) {
  const [open, setOpen] = useState(false);
  const colors = useThemeColors();
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
        className="h-[46px] flex-row items-center justify-between rounded-[9px] border border-line-strong bg-surface-1 px-[14px]">
        <Txt className={`text-[15px] ${value ? 'text-ink' : 'text-ink-faint'}`}>{value || placeholder}</Txt>
        <Txt className="text-[11px] text-ink-faint">▾</Txt>
      </Pressable>
      {hint ? (
        <Txt className="text-[11.5px] text-ink-faint" style={{ lineHeight: 16 }}>
          {hint}
        </Txt>
      ) : null}

      <Sheet visible={open} onClose={() => setOpen(false)} title={label}>
        <View className="gap-[1px] overflow-hidden rounded-[11px]" style={{ backgroundColor: colors.surface4 }}>
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
