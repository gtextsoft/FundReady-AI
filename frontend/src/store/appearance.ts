import { Appearance } from 'react-native';
import { create } from 'zustand';
import { colorScheme as nwColorScheme } from 'nativewind';
import { storage } from '@/lib/storage';
import type { ColorScheme } from '@/theme/tokens';

const KEY = 'fundready.appearance';

export type AppearancePreference = 'system' | 'light' | 'dark';

type AppearanceState = {
  preference: AppearancePreference;
  /** Resolved light/dark after applying system when preference is system. */
  resolved: ColorScheme;
  hydrated: boolean;
  hydrate(): Promise<void>;
  setPreference(preference: AppearancePreference): Promise<void>;
  /** Call when the OS scheme changes while preference is system. */
  syncSystem(system: ColorScheme | null | undefined): void;
};

function systemScheme(): ColorScheme {
  return Appearance.getColorScheme() === 'light' ? 'light' : 'dark';
}

function resolve(preference: AppearancePreference): ColorScheme {
  return preference === 'system' ? systemScheme() : preference;
}

function applyNativeWind(preference: AppearancePreference) {
  try {
    nwColorScheme.set(preference);
  } catch {
    // NativeWind may throw if darkMode is misconfigured — vars still drive UI.
  }
}

export const useAppearance = create<AppearanceState>((set, get) => ({
  preference: 'system',
  resolved: systemScheme(),
  hydrated: false,

  async hydrate() {
    const raw = await storage.get(KEY);
    const preference: AppearancePreference =
      raw === 'light' || raw === 'dark' || raw === 'system' ? raw : 'system';
    applyNativeWind(preference);
    set({ preference, resolved: resolve(preference), hydrated: true });
  },

  async setPreference(preference) {
    applyNativeWind(preference);
    await storage.set(KEY, preference);
    set({ preference, resolved: resolve(preference) });
  },

  syncSystem(system) {
    if (get().preference !== 'system') return;
    const resolved: ColorScheme = system === 'light' ? 'light' : 'dark';
    if (resolved !== get().resolved) set({ resolved });
  },
}));
