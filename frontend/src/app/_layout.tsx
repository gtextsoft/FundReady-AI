import { useEffect } from 'react';
import { Appearance, useColorScheme as useSystemColorScheme, View } from 'react-native';
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreen from 'expo-splash-screen';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useFonts } from 'expo-font';
import { vars } from 'nativewind';

import { Geist_400Regular } from '@expo-google-fonts/geist/400Regular';
import { Geist_500Medium } from '@expo-google-fonts/geist/500Medium';
import { Geist_600SemiBold } from '@expo-google-fonts/geist/600SemiBold';
import { GeistMono_400Regular } from '@expo-google-fonts/geist-mono/400Regular';
import { GeistMono_500Medium } from '@expo-google-fonts/geist-mono/500Medium';
import { GeistMono_600SemiBold } from '@expo-google-fonts/geist-mono/600SemiBold';

// Load-bearing side-effect imports. `global.css` is what puts the Tailwind
// output into the bundle at all — without this exact import every className in
// the app silently becomes a dead string. `css-interop` teaches the non-core
// components (Reanimated, LinearGradient) to forward className.
import '../global.css';
import '@/lib/css-interop';

import { useAppearance } from '@/store/appearance';
import { useSession } from '@/store/session';
import { paletteFor, themeVars } from '@/theme/tokens';

SplashScreen.preventAutoHideAsync();

function navigationTheme(scheme: 'light' | 'dark') {
  const base = scheme === 'light' ? DefaultTheme : DarkTheme;
  const p = paletteFor(scheme);
  return {
    ...base,
    colors: {
      ...base.colors,
      background: p.ground,
      card: p.ground,
      border: p.line,
      text: p.ink,
      primary: p.ink,
    },
  };
}

export default function RootLayout() {
  const restore = useSession((s) => s.restore);
  const hydrateAppearance = useAppearance((s) => s.hydrate);
  const syncSystem = useAppearance((s) => s.syncSystem);
  const resolved = useAppearance((s) => s.resolved);
  const hydrated = useAppearance((s) => s.hydrated);
  const systemScheme = useSystemColorScheme();

  const [fontsLoaded] = useFonts({
    Geist_400Regular,
    Geist_500Medium,
    Geist_600SemiBold,
    GeistMono_400Regular,
    GeistMono_500Medium,
    GeistMono_600SemiBold,
  });

  useEffect(() => {
    restore();
    void hydrateAppearance();
  }, [restore, hydrateAppearance]);

  useEffect(() => {
    syncSystem(systemScheme === 'light' ? 'light' : 'dark');
  }, [systemScheme, syncSystem]);

  useEffect(() => {
    const sub = Appearance.addChangeListener(({ colorScheme }) => {
      syncSystem(colorScheme === 'light' ? 'light' : 'dark');
    });
    return () => sub.remove();
  }, [syncSystem]);

  useEffect(() => {
    if (fontsLoaded && hydrated) SplashScreen.hideAsync();
  }, [fontsLoaded, hydrated]);

  if (!fontsLoaded || !hydrated) {
    return <View className="flex-1 bg-ground" style={vars(themeVars(resolved))} />;
  }

  const p = paletteFor(resolved);

  return (
    <SafeAreaProvider>
      <View className="flex-1" style={vars(themeVars(resolved))}>
        <ThemeProvider value={navigationTheme(resolved)}>
          <StatusBar style={resolved === 'light' ? 'dark' : 'light'} />
          <Stack
            screenOptions={{
              headerShown: false,
              contentStyle: { backgroundColor: p.ground },
              animation: 'fade',
            }}
          />
        </ThemeProvider>
      </View>
    </SafeAreaProvider>
  );
}
