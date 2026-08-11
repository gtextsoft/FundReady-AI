import { Text as RNText, type TextProps } from 'react-native';

/**
 * Text wrappers that bake in the right Geist family.
 *
 * Geist ships one font file per weight, so weight has to be chosen by family —
 * `font-semibold` and the other fontWeight utilities do nothing on custom
 * fonts in React Native. Use these instead of raw <Text>.
 */

type Props = TextProps & { className?: string };

/** `text-bone-secondary` and `text-obsidian` are colours; `text-[13px]` is a size. */
const HAS_COLOR = /(?:^|\s)text-(?!\[)/;

/**
 * Compose the family class with the default ink colour — but drop the default
 * when the caller supplies its own colour utility. Tailwind resolves competing
 * utilities by their order in the stylesheet, not by their order in the class
 * string, so leaving both in place would let `text-bone` silently beat a
 * caller's `text-obsidian` and paint white text on a white button.
 */
const join = (family: string, extra?: string) =>
  [family, extra && HAS_COLOR.test(extra) ? '' : 'text-bone', extra ?? ''].filter(Boolean).join(' ');

export function Txt({ className, ...rest }: Props) {
  return <RNText className={join('font-sans', className)} {...rest} />;
}

export function TxtMed({ className, ...rest }: Props) {
  return <RNText className={join('font-med', className)} {...rest} />;
}

export function TxtSemi({ className, ...rest }: Props) {
  return <RNText className={join('font-semi', className)} {...rest} />;
}

export function Mono({ className, ...rest }: Props) {
  return <RNText className={join('font-mono', className)} {...rest} />;
}

export function MonoMed({ className, ...rest }: Props) {
  return <RNText className={join('font-mono-med', className)} {...rest} />;
}

export function MonoSemi({ className, ...rest }: Props) {
  return <RNText className={join('font-mono-semi', className)} {...rest} />;
}

/** Small letter-spaced mono caps — the section eyebrows throughout the design. */
export function Eyebrow({ className, style, ...rest }: Props) {
  return (
    <RNText
      className={`font-mono text-[10px] text-bone-faint ${className ?? ''}`}
      style={[{ letterSpacing: 1.3 }, style]}
      {...rest}
    />
  );
}

/** Uppercase field label above every input. */
export function FieldLabel({ className, style, ...rest }: Props) {
  return (
    <RNText
      className={`font-med text-[11px] text-bone-secondary uppercase ${className ?? ''}`}
      style={[{ letterSpacing: 0.3 }, style]}
      {...rest}
    />
  );
}
