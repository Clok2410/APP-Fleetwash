import React, { useCallback, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
  Alert,
  Modal,
  TextInput,
} from "react-native";
import { useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { SafeAreaView } from "react-native-safe-area-context";
import { api } from "../../src/api";
import { useAuth } from "../../src/auth";
import { colors, spacing, radius, typography } from "../../src/theme";

export default function ScheduleScreen() {
  const { user } = useAuth();
  const [shifts, setShifts] = useState<any[]>([]);
  const [swaps, setSwaps] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [tab, setTab] = useState<"shifts" | "swaps">("shifts");
  const [swapModal, setSwapModal] = useState<{ shiftId: string } | null>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [swapTarget, setSwapTarget] = useState<string>("");
  const [swapReason, setSwapReason] = useState("");

  const load = useCallback(async () => {
    try {
      const [s, sw, u] = await Promise.all([
        api.get("/shifts"),
        api.get("/shifts/swaps"),
        api.get("/users"),
      ]);
      setShifts(s.data);
      setSwaps(sw.data);
      setUsers(u.data.filter((x: any) => x.id !== user?.id && x.role === "staff"));
    } catch {}
  }, [user?.id]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const submitSwap = async () => {
    if (!swapModal || !swapTarget) {
      Alert.alert("Pick a teammate");
      return;
    }
    try {
      await api.post(`/shifts/${swapModal.shiftId}/swap`, {
        target_user_id: swapTarget,
        reason: swapReason,
      });
      setSwapModal(null);
      setSwapTarget("");
      setSwapReason("");
      await load();
      Alert.alert("Swap requested");
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Failed");
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <View style={styles.header}>
        <Text style={typography.label}>Workforce</Text>
        <Text style={typography.h2}>My Schedule.</Text>
      </View>

      <View style={styles.tabs}>
        <TouchableOpacity
          testID="tab-shifts"
          onPress={() => setTab("shifts")}
          style={[styles.tab, tab === "shifts" && styles.tabActive]}
        >
          <Text style={[styles.tabText, tab === "shifts" && styles.tabTextActive]}>Shifts</Text>
        </TouchableOpacity>
        <TouchableOpacity
          testID="tab-swaps"
          onPress={() => setTab("swaps")}
          style={[styles.tab, tab === "swaps" && styles.tabActive]}
        >
          <Text style={[styles.tabText, tab === "swaps" && styles.tabTextActive]}>
            Swaps · {swaps.length}
          </Text>
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={async () => {
              setRefreshing(true);
              await load();
              setRefreshing(false);
            }}
          />
        }
      >
        {tab === "shifts" &&
          (shifts.length === 0 ? (
            <Empty message="No upcoming shifts. Your admin will assign them here." icon="calendar" />
          ) : (
            shifts.map((s) => (
              <View key={s.id} style={styles.shiftCard} testID={`shift-${s.id}`}>
                <View style={styles.shiftLeft}>
                  <Text style={typography.label}>{s.start?.slice(0, 10)}</Text>
                  <Text style={[typography.h3, { marginTop: 4 }]}>{s.title}</Text>
                  <Text style={typography.small}>
                    {s.start?.slice(11, 16)} – {s.end?.slice(11, 16)} · {s.location || "—"}
                  </Text>
                  {s.notes ? (
                    <Text style={[typography.small, { marginTop: 4 }]}>{s.notes}</Text>
                  ) : null}
                </View>
                <TouchableOpacity
                  testID={`swap-${s.id}`}
                  style={styles.swapBtn}
                  onPress={() => setSwapModal({ shiftId: s.id })}
                >
                  <Feather name="repeat" size={16} color={colors.primary} />
                </TouchableOpacity>
              </View>
            ))
          ))}

        {tab === "swaps" &&
          (swaps.length === 0 ? (
            <Empty message="No swap requests." icon="repeat" />
          ) : (
            swaps.map((s) => (
              <View key={s.id} style={styles.shiftCard}>
                <View style={styles.shiftLeft}>
                  <Text style={typography.label}>{s.status}</Text>
                  <Text style={[typography.h3, { marginTop: 4 }]}>
                    {s.from_user_name} → {s.to_user_name}
                  </Text>
                  {s.reason ? <Text style={typography.small}>{s.reason}</Text> : null}
                </View>
                <View
                  style={[
                    styles.statusPill,
                    s.status === "approved" && { backgroundColor: "#D1FAE5" },
                    s.status === "rejected" && { backgroundColor: "#FEE2E2" },
                  ]}
                >
                  <Text style={styles.statusText}>{s.status}</Text>
                </View>
              </View>
            ))
          ))}
      </ScrollView>

      <Modal visible={!!swapModal} animationType="slide" transparent onRequestClose={() => setSwapModal(null)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <Text style={typography.h3}>Request Swap</Text>
            <Text style={[typography.small, { marginBottom: spacing.md }]}>
              Choose a teammate to take this shift.
            </Text>
            <ScrollView style={{ maxHeight: 220 }}>
              {users.map((u) => (
                <TouchableOpacity
                  key={u.id}
                  style={[styles.userRow, swapTarget === u.id && styles.userRowActive]}
                  onPress={() => setSwapTarget(u.id)}
                >
                  <Feather name="user" size={16} color={colors.primary} />
                  <Text style={{ marginLeft: 10, fontWeight: "600" }}>{u.name}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
            <TextInput
              style={styles.input}
              placeholder="Reason (optional)"
              value={swapReason}
              onChangeText={setSwapReason}
              placeholderTextColor={colors.textMuted}
            />
            <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md }}>
              <TouchableOpacity style={[styles.btn, styles.btnGhost]} onPress={() => setSwapModal(null)}>
                <Text style={styles.btnGhostText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="swap-submit"
                style={[styles.btn, styles.btnPrimary]}
                onPress={submitSwap}
              >
                <Text style={styles.btnPrimaryText}>Send Request</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function Empty({ message, icon }: any) {
  return (
    <View style={styles.empty}>
      <Feather name={icon} size={28} color={colors.textMuted} />
      <Text style={[typography.body, { textAlign: "center", marginTop: 10 }]}>{message}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: { padding: spacing.lg, paddingBottom: 0 },
  tabs: { flexDirection: "row", padding: spacing.lg, gap: spacing.sm },
  tab: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: colors.surface },
  tabActive: { backgroundColor: colors.primary },
  tabText: { color: colors.textSecondary, fontWeight: "600" },
  tabTextActive: { color: "#fff" },
  list: { padding: spacing.lg, paddingTop: 0, gap: spacing.sm },
  shiftCard: {
    backgroundColor: "#fff",
    borderRadius: radius.lg,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    flexDirection: "row",
    alignItems: "center",
  },
  shiftLeft: { flex: 1 },
  swapBtn: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
  },
  statusPill: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
  },
  statusText: { fontSize: 11, fontWeight: "700", textTransform: "uppercase" },
  empty: { padding: spacing.xl, alignItems: "center" },
  modalBg: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.4)" },
  modalCard: {
    backgroundColor: "#fff",
    padding: spacing.lg,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
  },
  userRow: {
    flexDirection: "row",
    alignItems: "center",
    padding: 12,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    marginBottom: 6,
  },
  userRowActive: { backgroundColor: colors.brandSoft, borderWidth: 1, borderColor: colors.brand },
  input: {
    height: 48,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    marginTop: spacing.md,
  },
  btn: { flex: 1, height: 48, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  btnPrimary: { backgroundColor: colors.primary },
  btnPrimaryText: { color: "#fff", fontWeight: "700" },
  btnGhost: { backgroundColor: colors.surface },
  btnGhostText: { color: colors.primary, fontWeight: "700" },
});
