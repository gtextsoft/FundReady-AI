import { useAppearance } from '@/store/appearance';
import { paletteFor, type Palette } from '@/theme/tokens';

/** Resolved palette for the active appearance (light or dark). */
export function useThemeColors(): Palette {
  const resolved = useAppearance((s) => s.resolved);
  return paletteFor(resolved);
}
