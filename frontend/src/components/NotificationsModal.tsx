import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  Modal,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  StyleSheet,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { api } from "../api";
import { colors, spacing, radius, typography } from "../theme";

type Props = {
  visible: boolean;
  onClose: () => void;
  onChanged?: () => void;
};

export default function NotificationsModal({ visible, onClose, onChanged }: Props) {
  const [items, setItems] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setBusy(true);
    try {
      const { data } = await api.get("/notifications");
      setItems(data);
    } catch {} finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (visible) load();
  }, [visible]);

  const markRead = async (id: string) => {
    await api.post(`/notifications/${id}/read`);
    await load();
    onChanged?.();
  };

  const readAll = async () => {
    await api.post("/notifications/read-all");
    await load();
    onChanged?.();
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={{ flex: 1, backgroundColor: "#fff" }}>
        <View style={s.header}>
          <TouchableOpacity onPress={onClose}>
            <Feather name="x" size={24} color={colors.primary} />
          </TouchableOpacity>
          <Text style={[typography.h3, { marginLeft: 12, flex: 1 }]}>Notifications</Text>
          {items.some((i) => !i.read) && (
            <TouchableOpacity testID="read-all" onPress={readAll}>
              <Text style={{ color: colors.brand, fontWeight: "700" }}>Mark all read</Text>
            </TouchableOpacity>
          )}
        </View>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm }}>
          {busy ? (
            <ActivityIndicator color={colors.brand} />
          ) : items.length === 0 ? (
            <Text style={typography.body}>You're all caught up.</Text>
          ) : (
            items.map((n) => (
              <TouchableOpacity
                key={n.id}
                testID={`notif-${n.id}`}
                onPress={() => !n.read && markRead(n.id)}
                style={[s.card, !n.read && { borderLeftWidth: 3, borderLeftColor: colors.brand }]}
              >
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <View style={[s.iconBubble, { backgroundColor: n.kind === "off_site" ? "#FEE2E2" : colors.brandSoft }]}>
                    <Feather
                      name={n.kind === "off_site" ? "map-pin" : "alert-triangle"}
                      size={14}
                      color={n.kind === "off_site" ? colors.alert : colors.brand}
                    />
                  </View>
                  <View style={{ flex: 1, marginLeft: 10 }}>
                    <Text style={{ fontWeight: "700", color: colors.primary }}>{n.title}</Text>
                    <Text style={typography.small}>{n.body}</Text>
                    <Text style={[typography.small, { marginTop: 4, color: colors.textMuted }]}>
                      {new Date(n.created_at).toLocaleString()}
                    </Text>
                  </View>
                  {!n.read && <View style={s.dot} />}
                </View>
              </TouchableOpacity>
            ))
          )}
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

const s = StyleSheet.create({
  header: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.md,
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
  },
  card: {
    backgroundColor: "#fff",
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 12,
  },
  iconBubble: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brand, marginLeft: 6 },
});
