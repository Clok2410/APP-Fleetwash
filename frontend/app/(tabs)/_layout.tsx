import React, { useEffect } from "react";
import { Tabs, Redirect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { View, ActivityIndicator, StyleSheet, Platform } from "react-native";
import { useAuth } from "../../src/auth";
import { colors } from "../../src/theme";

export default function TabsLayout() {
  const { user } = useAuth();
  if (user === undefined)
    return (
      <View style={{ flex: 1, justifyContent: "center", alignItems: "center" }}>
        <ActivityIndicator color={colors.brand} />
      </View>
    );
  if (!user) return <Redirect href="/" />;

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarLabelStyle: { fontSize: 11, fontWeight: "600", letterSpacing: 0.3 },
        tabBarStyle: styles.tabBar,
        tabBarItemStyle: { paddingVertical: 6 },
      }}
    >
      <Tabs.Screen
        name="home"
        options={{
          title: "Home",
          tabBarIcon: ({ color }) => <Feather name="home" size={22} color={color} />,
        }}
      />
      <Tabs.Screen
        name="schedule"
        options={{
          title: "Schedule",
          tabBarIcon: ({ color }) => <Feather name="calendar" size={22} color={color} />,
        }}
      />
      <Tabs.Screen
        name="drive"
        options={{
          title: "Drive",
          tabBarIcon: ({ color }) => <Feather name="folder" size={22} color={color} />,
        }}
      />
      <Tabs.Screen
        name="forms"
        options={{
          title: "Forms",
          tabBarIcon: ({ color }) => <Feather name="file-text" size={22} color={color} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: "Profile",
          tabBarIcon: ({ color }) => <Feather name="user" size={22} color={color} />,
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    backgroundColor: "#FFFFFF",
    borderTopColor: colors.border,
    borderTopWidth: 1,
    height: Platform.OS === "ios" ? 84 : 64,
    paddingTop: 6,
  },
});
