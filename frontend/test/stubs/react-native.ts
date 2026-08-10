/**
 * Just enough `react-native` for the non-rendering modules.
 *
 * `Platform.OS` is 'web' so `lib/storage.ts` takes its `localStorage` branch
 * and `expo-secure-store` is never reached — the setup file supplies the
 * `localStorage` double.
 */
export const Platform = {
  OS: 'web' as const,
  select: <T,>(spec: { web?: T; default?: T; native?: T }): T | undefined =>
    spec.web ?? spec.default,
};
