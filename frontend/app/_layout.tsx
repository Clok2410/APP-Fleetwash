import { Stack } from "expo-router";
import { useEffect, useState } from "react";
import { View } from "react-native";
import { AuthProvider } from "../src/auth";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";

export default function RootLayout() {
  // SSR hydration gate — the Expo Web static export pre-renders every route at build time, but
  // SafeAreaProvider, Stack and Auth all read `window` / storage / `new Date()` on the client.
  // Rendering an empty shell at SSR keeps server + client first paint identical and eliminates
  // React minified hydration error #418.
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => setHydrated(true), []);
  if (!hydrated) {
    return <View style={{ flex: 1, backgroundColor: "#FFFFFF" }} />;
  }
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <StatusBar style="dark" />
        <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: "#FFFFFF" } }}>
          <Stack.Screen name="index" />
          <Stack.Screen name="(tabs)" />
          <Stack.Screen name="admin" options={{ presentation: "modal" }} />
        </Stack>
      </AuthProvider>
    </SafeAreaProvider>
  );
}
