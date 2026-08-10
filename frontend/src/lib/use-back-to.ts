import { useEffect } from 'react';
import { BackHandler, Platform } from 'react-native';
import { router, useNavigation, type Href } from 'expo-router';

/**
 * Sends the Android back button to one fixed destination.
 *
 * Used by the screens that come *after* the assessment is submitted. Their
 * natural back target is the form the answers were just sent from, and
 * returning to it invites someone to edit a copy of a profile the server has
 * already scored — so back means "dashboard" here, not "undo".
 *
 * Android only, deliberately: it is the one platform with a system back
 * button. iOS and web are handled by `replace` navigation plus the disabled
 * swipe gesture on the stack, because there is no event to intercept.
 */
export function useBackTo(destination: Href): void {
  const navigation = useNavigation();

  useEffect(() => {
    // Also stops the iOS/web swipe-back, which no listener can catch.
    navigation.setOptions({ gestureEnabled: false });
  }, [navigation]);

  useEffect(() => {
    if (Platform.OS !== 'android') return;
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      router.replace(destination);
      // Returning true tells Android the press was handled, which is what
      // stops the default pop.
      return true;
    });
    return () => subscription.remove();
  }, [destination]);
}
