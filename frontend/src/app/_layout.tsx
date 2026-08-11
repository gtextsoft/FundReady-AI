import { useEffect } from 'react';
import { View } from 'react-native';
import { DarkTheme, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreen from 'expo-splash-screen';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useFonts } from 'expo-font';

import { Archivo_400Regular } from '@expo-google-fonts/archivo/400Regular';
import { Archivo_500Medium } from '@expo-google-fonts/archivo/500Medium';
import { Archivo_600SemiBold } from '@expo-google-fonts/archivo/600SemiBold';
import { Archivo_700Bold } from '@expo-google-fonts/archivo/700Bold';
import { JetBrainsMono_400Regular } from '@expo-google-fonts/jetbrains-mono/400Regular';
import { JetBrainsMono_500Medium } from '@expo-google-fonts/jetbrains-mono/500Medium';
import { JetBrainsMono_600SemiBold } from '@expo-google-fonts/jetbrains-mono/600SemiBold';

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
const FundReadyTheme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    background: C.obsidian,
    card: C.obsidian,
    border: C.graphite,
    text: C.bone,
    primary: C.signal,
  },
};

export default function RootLayout() {
  const restore = useSession((s) => s.restore);

  const [fontsLoaded] = useFonts({
    Archivo_400Regular,
    Archivo_500Medium,
    Archivo_600SemiBold,
    Archivo_700Bold,
    JetBrainsMono_400Regular,
    JetBrainsMono_500Medium,
    JetBrainsMono_600SemiBold,
  });

  useEffect(() => {
    restore();
  }, [restore]);

  useEffect(() => {
    if (fontsLoaded) SplashScreen.hideAsync();
  }, [fontsLoaded]);

  if (!fontsLoaded) return <View className="flex-1 bg-obsidian" />;

  return (
    <SafeAreaProvider>
      <ThemeProvider value={FundReadyTheme}>
        <StatusBar style="light" />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: C.obsidian },
            animation: 'fade',
          }}
        />
      </ThemeProvider>
    </SafeAreaProvider>
  );
}
