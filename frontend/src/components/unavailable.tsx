import { Pressable, View } from 'react-native';
import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { useThemeColors } from '@/theme/use-theme-colors';
import { ApiFailure, isUnavailable } from '@/api';

/**
 * What a screen shows when its data does not exist yet.
 *
 * The app is ahead of the backend: several features are designed and built on
 * this side while their endpoints are still queued. Rather than fill the gap
 * with invented numbers, the screen says plainly that the feature is not built
 * — a blank panel is honest, a fake chart is not.
 */
export function Unavailable({
  title,
  error,
  className,
  onRetry,
}: {
  title: string;
  error: unknown;
  className?: string;
  /** Shown for real failures (network / server), not for not_implemented. */
  onRetry?: () => void;
}) {
  const colors = useThemeColors();
  const missing = isUnavailable(error);
  const message =
    error instanceof ApiFailure
      ? error.message
      : 'Something went wrong loading this. Try again in a moment.';

  return (
    <View
      className={`rounded-[12px] p-[14px] ${className ?? ''}`}
      style={{
        borderWidth: 1,
        borderStyle: missing ? 'dashed' : 'solid',
        borderColor: missing ? colors.lineDash : '#4a1d1d',
        backgroundColor: missing ? 'transparent' : 'rgba(255,77,79,0.08)',
      }}>
      <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: missing ? colors.inkFaint : colors.red }}>
        {missing ? 'NOT BUILT YET' : 'COULD NOT LOAD'}
      </Mono>
      <TxtSemi className="mb-[5px] mt-[9px] text-[15px]" style={{ letterSpacing: -0.3 }}>
        {title}
      </TxtSemi>
      <Txt className="text-[12.5px] text-ink-muted" style={{ lineHeight: 19 }}>
        {message}
      </Txt>
      {!missing && onRetry ? (
        <Pressable
          accessibilityRole="button"
          onPress={onRetry}
          className="mt-3 self-start rounded-[8px] border border-line px-3 py-2">
          <TxtSemi className="text-[12px]">Try again</TxtSemi>
        </Pressable>
      ) : null}
    </View>
  );
}
