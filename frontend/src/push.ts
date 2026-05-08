// Expo Push Notifications registration helper.
// Safe on web — short-circuits if Notifications module / Constants aren't usable.
import { Platform } from "react-native";
import { api } from "./api";

let registered = false;

export async function registerForPushAsync() {
  if (registered) return;
  if (Platform.OS === "web") return; // web doesn't support Expo push
  try {
    const Notifications = await import("expo-notifications");
    const Device = await import("expo-device");

    // Foreground notification handler — show banner + sound.
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowAlert: true,
        shouldShowBanner: true,
        shouldShowList: true,
        shouldPlaySound: true,
        shouldSetBadge: true,
      }),
    });

    if (!Device.isDevice) {
      // Push only works on physical devices (or sim with proper config).
      return;
    }

    let { status } = await Notifications.getPermissionsAsync();
    if (status !== "granted") {
      const r = await Notifications.requestPermissionsAsync();
      status = r.status;
    }
    if (status !== "granted") return;

    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("default", {
        name: "default",
        importance: Notifications.AndroidImportance.HIGH,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: "#0F172A",
      });
    }

    let projectId: string | undefined;
    try {
      const Constants = (await import("expo-constants")).default as any;
      projectId =
        Constants?.expoConfig?.extra?.eas?.projectId ||
        Constants?.easConfig?.projectId ||
        undefined;
    } catch {}

    const tokenRes = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined
    );
    const token = tokenRes?.data;
    if (!token) return;

    await api.post("/users/me/push-token", { token });
    registered = true;
  } catch {
    // Silently ignore — push is best-effort.
  }
}

export async function unregisterPush() {
  registered = false;
  try {
    await api.post("/users/me/push-token", { token: "" });
  } catch {}
}
