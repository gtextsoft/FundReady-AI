import { useEffect } from 'react';
import { View } from 'react-native';
import { DarkTheme, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreen from 'expo-splash-screen';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useFonts } from 'expo-font';

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

import { C } from '@/theme/tokens';
import { useSession } from '@/store/session';

SplashScreen.preventAutoHideAsync();

/**
 * React Navigation paints its own theme background behind every screen —
 * DefaultTheme's #f2f2f2 shows through as a light flash on navigation and
 * behind the web document. The app is dark on every surface.
 */
const FundMeTheme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    background: C.ground,
    card: C.ground,
    border: C.line,
    text: C.ink,
    primary: C.ink,
  },
};

export default function RootLayout() {
  const restore = useSession((s) => s.restore);

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
  }, [restore]);

  useEffect(() => {
    if (fontsLoaded) SplashScreen.hideAsync();
  }, [fontsLoaded]);

  if (!fontsLoaded) return <View className="flex-1 bg-ground" />;

  return (
    <SafeAreaProvider>
      <ThemeProvider value={FundMeTheme}>
        <StatusBar style="light" />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: C.ground },
            animation: 'fade',
          }}
        />
      </ThemeProvider>
    </SafeAreaProvider>
  );
}
