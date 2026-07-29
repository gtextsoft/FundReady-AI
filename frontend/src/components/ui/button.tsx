import { ActivityIndicator, Pressable, type PressableProps } from 'react-native';
import { TxtSemi, TxtMed } from './text';
import { C } from '@/theme/tokens';

type Variant = 'primary' | 'secondary' | 'amber' | 'green';

type Props = Omit<PressableProps, 'children'> & {
  label: string;
  variant?: Variant;
  height?: number;
  loading?: boolean;
  className?: string;
};

const SURFACE: Record<Variant, string> = {
  primary: 'bg-ink border border-ink',
  secondary: 'bg-transparent border border-line-strong',
  amber: 'bg-amb border border-amb',
  green: 'bg-grn border border-grn',
};

const LABEL: Record<Variant, string> = {
  primary: 'text-ground',
  secondary: 'text-ink',
  amber: 'text-[#0a0a0a]',
  green: 'text-[#04150c]',
};

const SPINNER: Record<Variant, string> = {
  primary: C.ground,
  secondary: C.ink,
  amber: '#0a0a0a',
  green: '#04150c',
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
