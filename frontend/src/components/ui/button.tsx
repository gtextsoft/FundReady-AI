import { ActivityIndicator, Pressable, type PressableProps } from 'react-native';
import { TxtSemi, TxtMed } from './text';
import { C } from '@/theme/tokens';

/**
 * `primary` is signal green, because the brand reserves signal for AI output
 * and the primary action and nothing else. `flag` is for an action that closes
 * a specific gap. There is no third accent — a button that is neither of those
 * is `secondary`.
 */
type Variant = 'primary' | 'secondary' | 'flag';

type Props = Omit<PressableProps, 'children'> & {
  label: string;
  variant?: Variant;
  height?: number;
  loading?: boolean;
  className?: string;
};

const SURFACE: Record<Variant, string> = {
  primary: 'bg-signal border border-signal',
  secondary: 'bg-transparent border border-graphite-strong',
  flag: 'bg-flag border border-flag',
};

// Both accents are light enough that bone-on-accent falls under 4.5:1;
// obsidian clears 7:1 on each.
const LABEL: Record<Variant, string> = {
  primary: 'text-obsidian',
  secondary: 'text-bone',
  flag: 'text-obsidian',
};

const SPINNER: Record<Variant, string> = {
  primary: C.obsidian,
  secondary: C.bone,
  flag: C.obsidian,
};

export function Button({
  label,
  variant = 'primary',
  height = 48,
  loading = false,
  className,
  disabled,
  ...rest
}: Props) {
  const Label = variant === 'secondary' ? TxtMed : TxtSemi;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled || loading }}
      disabled={disabled || loading}
      className={`w-full flex-row items-center justify-center gap-[9px] rounded-[10px] ${SURFACE[variant]} ${
        disabled || loading ? 'opacity-60' : ''
      } ${className ?? ''}`}
      style={{ height }}
      {...rest}>
      {loading ? (
        <ActivityIndicator size="small" color={SPINNER[variant]} />
      ) : (
        <Label className={`text-[15px] ${LABEL[variant]}`}>{label}</Label>
      )}
    </Pressable>
  );
}
