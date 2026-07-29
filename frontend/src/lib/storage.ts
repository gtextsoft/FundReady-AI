import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

/**
 * Token storage. SecureStore is native-only, so web falls back to
 * localStorage — good enough for a browser preview, and the native builds
 * (the ones that ship) still get the keychain.
 */
export const storage = {
  async get(key: string): Promise<string | null> {
    if (Platform.OS === 'web') {
      try {
        return globalThis.localStorage?.getItem(key) ?? null;
      } catch {
        return null;
      }
    }
    return SecureStore.getItemAsync(key);
  },

  async set(key: string, value: string): Promise<void> {
    if (Platform.OS === 'web') {
      try {
        globalThis.localStorage?.setItem(key, value);
      } catch {
        /* private mode — session simply will not persist */
      }
      return;
    }
    await SecureStore.setItemAsync(key, value);
  },

  async remove(key: string): Promise<void> {
    if (Platform.OS === 'web') {
      try {
        globalThis.localStorage?.removeItem(key);
      } catch {
        /* ignore */
      }
      return;
    }
    await SecureStore.deleteItemAsync(key);
  },
};
