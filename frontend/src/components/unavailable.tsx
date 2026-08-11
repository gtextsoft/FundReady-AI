import { View } from 'react-native';
import { Mono, Txt, TxtSemi } from '@/components/ui/text';
import { C } from '@/theme/tokens';
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
}: {
  title: string;
  error: unknown;
  className?: string;
}) {
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
        borderColor: missing ? C.graphiteBright : '#4A1F1E',
        backgroundColor: missing ? 'transparent' : 'rgba(242,85,78,0.08)',
      }}>
      <Mono className="text-[9px]" style={{ letterSpacing: 1.2, color: missing ? C.boneFaint : C.alert }}>
        {missing ? 'NOT BUILT YET' : 'COULD NOT LOAD'}
      </Mono>
      <TxtSemi className="mb-[5px] mt-[9px] text-[15px]" style={{ letterSpacing: -0.3 }}>
        {title}
      </TxtSemi>
      <Txt className="text-[12.5px] text-bone-secondary" style={{ lineHeight: 19 }}>
        {message}
      </Txt>
    </View>
  );
}
