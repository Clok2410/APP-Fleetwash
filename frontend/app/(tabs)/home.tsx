import React, { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  RefreshControl,
  Alert,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { SafeAreaView } from "react-native-safe-area-context";
import * as Location from "expo-location";
import { api } from "../../src/api";
import { useAuth } from "../../src/auth";
import { colors, spacing, radius, typography } from "../../src/theme";

function fmtDuration(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export default function HomeScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const [status, setStatus] = useState<{ clocked_in: boolean; entry: any } | null>(null);
  const [balance, setBalance] = useState<any>(null);
  const [todayShifts, setTodayShifts] = useState<any[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, b, sh] = await Promise.all([
        api.get("/clock/status"),
        api.get("/holidays/balance"),
        api.get("/shifts"),
      ]);
      setStatus(s.data);
      setBalance(b.data);
      const today = new Date().toISOString().slice(0, 10);
      setTodayShifts((sh.data || []).filter((x: any) => (x.start || "").slice(0, 10) === today));
      if (user?.role === "admin") {
        try {
          const a = await api.get("/admin/checklist-alerts");
          setAlerts(a.data || []);
        } catch {}
      }
    } catch (e: any) {
      // silent
    }
  }, [user?.role]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  useEffect(() => {
    const t = setInterval(() => setTick((v) => v + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const elapsed = (() => {
    if (!status?.clocked_in || !status.entry?.clock_in) return 0;
    const start = new Date(status.entry.clock_in).getTime();
    return Math.max(0, Math.floor((Date.now() - start) / 1000));
  })();

  const handleClockIn = async () => {
    setBusy(true);
    try {
      let loc: string | null = null;
      try {
        const { status: perm } = await Location.requestForegroundPermissionsAsync();
        if (perm === "granted") {
          const pos = await Location.getCurrentPositionAsync({});
          loc = `${pos.coords.latitude.toFixed(4)},${pos.coords.longitude.toFixed(4)}`;
        }
      } catch {}
      await api.post("/clock/in", { location: loc });
      await load();
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Could not clock in");
    } finally {
      setBusy(false);
    }
  };

  const handleClockOut = async () => {
    setBusy(true);
    try {
      await api.post("/clock/out", {});
      await load();
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Could not clock out");
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <ScrollView
        contentContainerStyle={styles.container}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        <View style={styles.headerRow}>
          <View>
            <Text style={typography.label}>Welcome back</Text>
            <Text style={[typography.h2, { marginTop: 4 }]}>{user?.name}.</Text>
          </View>
          {user?.role === "admin" && (
            <TouchableOpacity
              testID="open-admin"
              style={styles.adminPill}
              onPress={() => router.push("/admin")}
            >
              <Feather name="shield" size={14} color="#fff" />
              <Text style={styles.adminPillText}>Admin</Text>
            </TouchableOpacity>
          )}
        </View>

        <View style={styles.clockCard}>
          <Text style={typography.label}>{status?.clocked_in ? "On the clock" : "Off the clock"}</Text>
          <Text style={styles.timer}>
            {status?.clocked_in ? fmtDuration(elapsed) : "Ready to start"}
          </Text>
          <TouchableOpacity
            testID={status?.clocked_in ? "clock-out-button" : "clock-in-button"}
            disabled={busy}
            onPress={status?.clocked_in ? handleClockOut : handleClockIn}
            activeOpacity={0.85}
            style={[
              styles.clockButton,
              { backgroundColor: status?.clocked_in ? colors.alert : colors.brand },
            ]}
          >
            {busy ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <>
                <Feather
                  name={status?.clocked_in ? "log-out" : "play-circle"}
                  size={28}
                  color="#fff"
                />
                <Text style={styles.clockBtnText}>
                  {status?.clocked_in ? "Clock Out" : "Clock In"}
                </Text>
              </>
            )}
          </TouchableOpacity>
        </View>

        <View style={styles.statsRow}>
          <View style={styles.statCard}>
            <Text style={typography.label}>Holidays Left</Text>
            <Text style={styles.statBig}>{balance ? balance.remaining : "–"}</Text>
            <Text style={typography.small}>
              of {balance?.entitlement || 0} days · {balance?.pending || 0} pending
            </Text>
          </View>
          <View style={styles.statCard}>
            <Text style={typography.label}>Today's Shifts</Text>
            <Text style={styles.statBig}>{todayShifts.length}</Text>
            <Text style={typography.small}>
              {todayShifts[0] ? todayShifts[0].title : "Nothing scheduled"}
            </Text>
          </View>
        </View>

        {user?.role === "admin" && alerts.length > 0 && (
          <View style={styles.alertCard} testID="admin-alerts">
            <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 8 }}>
              <Feather name="alert-triangle" size={16} color={colors.alert} />
              <Text style={[typography.label, { marginLeft: 6, color: colors.alert }]}>
                {alerts.length} checklist{alerts.length > 1 ? "s" : ""} need attention today
              </Text>
            </View>
            {alerts.map((a) => (
              <TouchableOpacity
                key={a.template_id}
                style={styles.alertRow}
                testID={`alert-${a.template_id}`}
                onPress={() => router.push("/admin")}
              >
                <View style={{ flex: 1 }}>
                  <Text style={{ fontWeight: "700", color: colors.primary }}>{a.title}</Text>
                  <Text style={typography.small}>
                    {a.reason} · {a.overall_percent}% / target {a.target_percent}%
                  </Text>
                </View>
                <Feather name="chevron-right" size={16} color={colors.textMuted} />
              </TouchableOpacity>
            ))}
          </View>
        )}

        <View style={{ marginTop: spacing.lg }}>
          <Text style={typography.label}>Quick Actions</Text>
          <View style={styles.quickGrid}>
            <QuickAction
              icon="calendar"
              label="Request Holiday"
              onPress={() => router.push("/(tabs)/profile")}
            />
            <QuickAction
              icon="folder"
              label="Shared Drive"
              onPress={() => router.push("/(tabs)/drive")}
            />
            <QuickAction
              icon="file-text"
              label="Fillable Forms"
              onPress={() => router.push("/(tabs)/forms")}
            />
            <QuickAction
              icon="clock"
              label="My Schedule"
              onPress={() => router.push("/(tabs)/schedule")}
            />
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function QuickAction({ icon, label, onPress }: any) {
  return (
    <TouchableOpacity
      testID={`qa-${label.toLowerCase().replace(/\s/g, "-")}`}
      style={styles.qa}
      activeOpacity={0.8}
      onPress={onPress}
    >
      <View style={styles.qaIcon}>
        <Feather name={icon} size={18} color={colors.primary} />
      </View>
      <Text style={styles.qaText}>{label}</Text>
      <Feather name="arrow-right" size={16} color={colors.textMuted} />
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  container: { padding: spacing.lg, paddingBottom: spacing.xxl },
  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  adminPill: {
    backgroundColor: colors.primary,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: radius.pill,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  adminPillText: { color: "#fff", fontWeight: "600", fontSize: 12 },
  clockCard: {
    marginTop: spacing.lg,
    backgroundColor: colors.surface,
    borderRadius: radius.xl,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
  },
  timer: { fontSize: 36, fontWeight: "700", color: colors.primary, marginVertical: spacing.md },
  clockButton: {
    width: "100%",
    height: 64,
    borderRadius: radius.pill,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
  },
  clockBtnText: { color: "#fff", fontSize: 18, fontWeight: "700" },
  statsRow: { flexDirection: "row", gap: spacing.md, marginTop: spacing.lg },
  statCard: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  statBig: { fontSize: 32, fontWeight: "700", color: colors.primary, marginVertical: 4 },
  quickGrid: { marginTop: spacing.sm, gap: spacing.sm },
  qa: {
    backgroundColor: "#fff",
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
  },
  qaIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.md,
    backgroundColor: colors.brandSoft,
    alignItems: "center",
    justifyContent: "center",
  },
  qaText: { flex: 1, fontSize: 15, fontWeight: "600", color: colors.primary },
  alertCard: {
    marginTop: spacing.lg,
    backgroundColor: "#FEF2F2",
    borderRadius: radius.lg,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: "#FECACA",
  },
  alertRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 10,
    borderTopColor: "#FECACA",
    borderTopWidth: 1,
  },
});
