import React, { useCallback, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  Modal,
  TextInput,
  RefreshControl,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { SafeAreaView } from "react-native-safe-area-context";
import { Calendar } from "react-native-calendars";
import { api } from "../../src/api";
import { useAuth } from "../../src/auth";
import { colors, spacing, radius, typography } from "../../src/theme";

export default function ProfileScreen() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [requests, setRequests] = useState<any[]>([]);
  const [balance, setBalance] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [weekly, setWeekly] = useState<any>(null);
  const [accrual, setAccrual] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [reqOpen, setReqOpen] = useState(false);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [reason, setReason] = useState("");
  const [type, setType] = useState<"annual" | "sick" | "unpaid">("annual");
  const [mode, setMode] = useState<"single" | "range">("single");

  // Count of days (inclusive) selected — 0 if nothing chosen
  const dayCount = (() => {
    if (!start) return 0;
    const e = end || start;
    const s = new Date(start + "T00:00:00");
    const eD = new Date(e + "T00:00:00");
    const ms = eD.getTime() - s.getTime();
    return Math.max(1, Math.floor(ms / 86400000) + 1);
  })();

  const load = useCallback(async () => {
    try {
      const [r, b, h, w, a] = await Promise.all([
        api.get("/holidays/requests"),
        api.get("/holidays/balance"),
        api.get("/clock/history"),
        api.get("/clock/weekly-summary").catch(() => ({ data: null })),
        api.get("/clock/accrual").catch(() => ({ data: null })),
      ]);
      setRequests(r.data);
      setBalance(b.data);
      setHistory(h.data.slice(0, 10));
      setWeekly(w.data);
      setAccrual(a.data);
    } catch {}
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const submitRequest = async () => {
    if (!start) {
      Alert.alert("Pick a date", "Tap a date on the calendar to select your holiday.");
      return;
    }
    const effectiveEnd = end || start; // single-day defaults end -> start
    try {
      await api.post("/holidays/requests", { start_date: start, end_date: effectiveEnd, reason, type });
      setReqOpen(false);
      setStart("");
      setEnd("");
      setReason("");
      await load();
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Failed");
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <ScrollView
        contentContainerStyle={styles.container}
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
        <View style={styles.profileCard}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{user?.name?.[0]?.toUpperCase() || "?"}</Text>
          </View>
          <Text style={typography.h2}>{user?.name}</Text>
          <Text style={typography.small}>{user?.email}</Text>
          <View style={styles.rolePill}>
            <Feather
              name={user?.role === "admin" ? "shield" : "user"}
              size={12}
              color={colors.brand}
            />
            <Text style={styles.rolePillText}>{user?.role?.toUpperCase()}</Text>
          </View>
        </View>

        {balance && (
          <View style={styles.row3}>
            <Stat label="Total" value={balance.entitlement} />
            <Stat label="Used" value={balance.used} color={colors.alert} />
            <Stat label="Left" value={balance.remaining} color={colors.success} />
          </View>
        )}

        {/* Time Clock card — weekly Mon→Sun total + holiday accrual */}
        {weekly && (
          <View style={styles.section} testID="time-clock-card">
            <View style={styles.sectionHead}>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <Feather name="clock" size={16} color={colors.brand} />
                <Text style={[typography.label, { marginLeft: 6 }]}>Time Clock</Text>
              </View>
              <Text style={[typography.small, { color: colors.textMuted }]}>
                {weekly.week_start} → {weekly.week_end}
              </Text>
            </View>
            <View style={styles.row3}>
              <Stat label="This Week" value={`${weekly.total_hours}h`} color={colors.brand} />
              <Stat
                label="Breaks"
                value={`${weekly.break_hours}h`}
                color={colors.textMuted as any}
              />
              <Stat
                label="Net"
                value={`${weekly.net_hours}h`}
                color={colors.success}
              />
            </View>
            {/* Per-day bars */}
            <View style={styles.weekBars}>
              {weekly.days.map((d: any, i: number) => {
                const max = Math.max(1, ...weekly.days.map((x: any) => x.hours || 0));
                const pct = ((d.hours || 0) / max) * 100;
                const labels = ["M", "T", "W", "T", "F", "S", "S"];
                return (
                  <View key={d.date} style={{ flex: 1, alignItems: "center" }}>
                    <View style={styles.weekBarTrack}>
                      <View
                        style={[
                          styles.weekBarFill,
                          { height: `${pct}%`, backgroundColor: d.hours > 0 ? colors.brand : colors.border },
                        ]}
                      />
                    </View>
                    <Text style={[typography.small, { color: colors.textMuted, marginTop: 4 }]}>
                      {labels[i]}
                    </Text>
                    <Text style={[typography.small, { fontSize: 10, fontWeight: "700", color: colors.primary }]}>
                      {d.hours > 0 ? `${d.hours}h` : "—"}
                    </Text>
                  </View>
                );
              })}
            </View>
            {/* Accrual badge */}
            {accrual && (
              <View style={styles.accrualBadge}>
                <Feather name="gift" size={14} color={colors.brand} />
                <Text style={[typography.small, { marginLeft: 6, color: colors.primary, fontWeight: "600" }]}>
                  Earned {accrual.accrued_holiday_hours}h holiday pay this year
                </Text>
                <Text style={[typography.small, { color: colors.textMuted, marginLeft: 4, fontSize: 11 }]}>
                  ({accrual.net_hours}h net worked)
                </Text>
              </View>
            )}
            <Text style={[typography.small, { color: colors.textMuted, fontSize: 11, marginTop: 4 }]}>
              Rule: 1h holiday per 3h worked, less 30min break per 8h shift.
            </Text>
          </View>
        )}

        <View style={styles.section}>
          <View style={styles.sectionHead}>
            <Text style={typography.label}>Holiday Requests</Text>
            <TouchableOpacity testID="new-holiday-btn" style={styles.addBtn} onPress={() => setReqOpen(true)}>
              <Feather name="plus" size={14} color="#fff" />
              <Text style={{ color: "#fff", fontWeight: "600", marginLeft: 4, fontSize: 13 }}>
                Request
              </Text>
            </TouchableOpacity>
          </View>
          {requests.length === 0 ? (
            <Text style={[typography.small, { paddingVertical: 16 }]}>No requests yet.</Text>
          ) : (
            requests.map((r) => (
              <View key={r.id} style={styles.requestRow}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontWeight: "600", color: colors.primary }}>
                    {r.start_date} → {r.end_date}
                  </Text>
                  <Text style={typography.small}>
                    {r.type} {r.reason ? `· ${r.reason}` : ""}
                  </Text>
                </View>
                <View
                  style={[
                    styles.statusPill,
                    r.status === "approved" && { backgroundColor: "#D1FAE5" },
                    r.status === "rejected" && { backgroundColor: "#FEE2E2" },
                  ]}
                >
                  <Text style={styles.statusText}>{r.status}</Text>
                </View>
              </View>
            ))
          )}
        </View>

        <View style={styles.section}>
          <Text style={typography.label}>Recent Clock Entries</Text>
          {history.length === 0 ? (
            <Text style={[typography.small, { paddingVertical: 16 }]}>No entries yet.</Text>
          ) : (
            history.map((h) => (
              <View key={h.id} style={styles.requestRow}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontWeight: "600", color: colors.primary }}>
                    {h.clock_in?.slice(0, 10)}
                  </Text>
                  <Text style={typography.small}>
                    {h.clock_in?.slice(11, 16)} – {h.clock_out ? h.clock_out.slice(11, 16) : "open"}
                  </Text>
                </View>
                <Text style={{ fontWeight: "700", color: colors.primary }}>
                  {h.duration_seconds
                    ? `${Math.floor(h.duration_seconds / 3600)}h ${Math.floor((h.duration_seconds % 3600) / 60)}m`
                    : "—"}
                </Text>
              </View>
            ))
          )}
        </View>

        {user?.role === "admin" && (
          <TouchableOpacity
            testID="open-admin-from-profile"
            style={[styles.btn, { marginBottom: spacing.sm, backgroundColor: colors.brand }]}
            onPress={() => router.push("/admin")}
          >
            <Feather name="shield" size={16} color="#fff" />
            <Text style={[styles.btnText, { color: "#fff", marginLeft: 8 }]}>Admin Panel</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity testID="logout-btn" style={[styles.btn, styles.btnDanger]} onPress={logout}>
          <Feather name="log-out" size={16} color={colors.alert} />
          <Text style={[styles.btnText, { color: colors.alert, marginLeft: 8 }]}>Sign Out</Text>
        </TouchableOpacity>
      </ScrollView>

      <Modal visible={reqOpen} animationType="slide" transparent onRequestClose={() => setReqOpen(false)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <Text style={typography.h3}>Request Holiday</Text>

            {/* Type chips */}
            <View style={{ flexDirection: "row", gap: 8, marginTop: spacing.md }}>
              {(["annual", "sick", "unpaid"] as const).map((t) => (
                <TouchableOpacity
                  key={t}
                  onPress={() => setType(t)}
                  style={[styles.typeChip, type === t && { backgroundColor: colors.primary }]}
                >
                  <Text style={{ color: type === t ? "#fff" : colors.primary, fontWeight: "600", fontSize: 13 }}>
                    {t}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            {/* Single day / Date range toggle */}
            <View style={{ flexDirection: "row", gap: 8, marginTop: spacing.md }}>
              <TouchableOpacity
                testID="mode-single"
                onPress={() => {
                  setMode("single");
                  // Keep the chosen start if any; clear end so it's treated as single day
                  setEnd("");
                }}
                style={[styles.modeChip, mode === "single" && styles.modeChipActive]}
              >
                <Feather
                  name="calendar"
                  size={14}
                  color={mode === "single" ? "#fff" : colors.primary}
                  style={{ marginRight: 6 }}
                />
                <Text
                  style={{
                    color: mode === "single" ? "#fff" : colors.primary,
                    fontWeight: "600",
                    fontSize: 13,
                  }}
                >
                  Single day
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="mode-range"
                onPress={() => setMode("range")}
                style={[styles.modeChip, mode === "range" && styles.modeChipActive]}
              >
                <Feather
                  name="calendar"
                  size={14}
                  color={mode === "range" ? "#fff" : colors.primary}
                  style={{ marginRight: 6 }}
                />
                <Text
                  style={{
                    color: mode === "range" ? "#fff" : colors.primary,
                    fontWeight: "600",
                    fontSize: 13,
                  }}
                >
                  Date range
                </Text>
              </TouchableOpacity>
            </View>

            {/* Selection summary */}
            <Text
              testID="holiday-summary"
              style={[typography.small, { marginTop: spacing.md, marginBottom: 6 }]}
            >
              {!start
                ? mode === "single"
                  ? "Tap the day you want off."
                  : "Tap a start date, then an end date."
                : mode === "single"
                ? `Requesting 1 day: ${start}`
                : !end
                ? `Start: ${start}. Now tap an end date (or switch to Single day).`
                : `Requesting ${dayCount} day${dayCount === 1 ? "" : "s"}: ${start} → ${end}`}
            </Text>

            <View style={{ borderRadius: radius.md, overflow: "hidden", borderWidth: 1, borderColor: colors.border }}>
              <Calendar
                testID="holiday-calendar"
                onDayPress={(d: any) => {
                  if (mode === "single") {
                    // One-tap selection: just set start, clear end
                    setStart(d.dateString);
                    setEnd("");
                    return;
                  }
                  // Range mode: two-tap selection
                  if (!start || (start && end)) {
                    setStart(d.dateString);
                    setEnd("");
                  } else if (d.dateString < start) {
                    setStart(d.dateString);
                  } else if (d.dateString === start) {
                    // Tapping same day in range mode → treat as 1-day range
                    setEnd(d.dateString);
                  } else {
                    setEnd(d.dateString);
                  }
                }}
                markingType="period"
                markedDates={(() => {
                  const m: any = {};
                  if (start && (mode === "single" || !end)) {
                    m[start] = { startingDay: true, endingDay: true, color: colors.primary, textColor: "#fff" };
                  } else if (start && end) {
                    const sD = new Date(start);
                    const eD = new Date(end);
                    const cur = new Date(sD);
                    while (cur <= eD) {
                      const ds = cur.toISOString().slice(0, 10);
                      m[ds] = {
                        color: colors.primary,
                        textColor: "#fff",
                        startingDay: ds === start,
                        endingDay: ds === end,
                      };
                      cur.setDate(cur.getDate() + 1);
                    }
                  }
                  return m;
                })()}
                theme={{
                  todayTextColor: colors.brand,
                  arrowColor: colors.primary,
                }}
              />
            </View>

            {start ? (
              <TouchableOpacity
                testID="holiday-clear"
                onPress={() => {
                  setStart("");
                  setEnd("");
                }}
                style={{ alignSelf: "flex-end", marginTop: 6 }}
              >
                <Text style={{ color: colors.primary, fontWeight: "600", fontSize: 12 }}>Clear</Text>
              </TouchableOpacity>
            ) : null}

            <TextInput
              style={[styles.input, { height: 64, marginTop: spacing.sm }]}
              placeholder="Reason (optional)"
              value={reason}
              onChangeText={setReason}
              multiline
              placeholderTextColor={colors.textMuted}
            />
            <View style={{ flexDirection: "row", gap: 8, marginTop: spacing.md }}>
              <TouchableOpacity style={[styles.modalBtn, { backgroundColor: colors.surface }]} onPress={() => setReqOpen(false)}>
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="submit-holiday"
                style={[
                  styles.modalBtn,
                  { backgroundColor: start ? colors.primary : colors.border },
                ]}
                onPress={submitRequest}
                disabled={!start}
              >
                <Text style={{ color: "#fff", fontWeight: "700" }}>
                  {start ? `Submit · ${dayCount} day${dayCount === 1 ? "" : "s"}` : "Submit"}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function Stat({ label, value, color }: any) {
  return (
    <View style={styles.statBox}>
      <Text style={typography.label}>{label}</Text>
      <Text style={[styles.statValue, color && { color }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  container: { padding: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.md },
  profileCard: {
    alignItems: "center",
    padding: spacing.lg,
    backgroundColor: colors.surface,
    borderRadius: radius.xl,
  },
  avatar: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 12,
  },
  avatarText: { color: "#fff", fontSize: 28, fontWeight: "700" },
  rolePill: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brandSoft,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    marginTop: 8,
  },
  rolePillText: { color: colors.brand, fontWeight: "700", fontSize: 11, marginLeft: 4, letterSpacing: 1 },
  row3: { flexDirection: "row", gap: 8 },
  statBox: {
    flex: 1,
    padding: spacing.md,
    backgroundColor: "#fff",
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  statValue: { fontSize: 24, fontWeight: "700", color: colors.primary, marginTop: 4 },
  section: {
    backgroundColor: "#fff",
    borderRadius: radius.lg,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  sectionHead: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  addBtn: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.primary,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: radius.pill,
  },
  requestRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 10,
    borderTopColor: colors.border,
    borderTopWidth: 1,
  },
  statusPill: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
  },
  statusText: { fontSize: 11, fontWeight: "700", textTransform: "uppercase" },
  btn: {
    flexDirection: "row",
    height: 52,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
  },
  btnDanger: { backgroundColor: "#FEE2E2" },
  btnText: { fontWeight: "700", fontSize: 15 },
  modalBg: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.4)" },
  modalCard: { backgroundColor: "#fff", padding: spacing.lg, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl },
  typeChip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
  },
  modeChip: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  modeChipActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  weekBars: {
    flexDirection: "row",
    alignItems: "flex-end",
    justifyContent: "space-between",
    marginTop: 10,
    paddingHorizontal: 4,
  },
  weekBarTrack: {
    width: "70%",
    height: 60,
    backgroundColor: colors.surface,
    borderRadius: 6,
    justifyContent: "flex-end",
    overflow: "hidden",
  },
  weekBarFill: {
    width: "100%",
    borderRadius: 6,
    minHeight: 2,
  },
  accrualBadge: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brandSoft,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: radius.md,
    marginTop: 12,
    flexWrap: "wrap",
  },
  input: {
    height: 48,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    marginTop: spacing.sm,
    color: colors.textPrimary,
  },
  modalBtn: { flex: 1, height: 48, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
});
