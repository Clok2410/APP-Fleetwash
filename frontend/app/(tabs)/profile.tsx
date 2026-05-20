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
  Platform,
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
  const [eligibility, setEligibility] = useState<any>(null);
  const [profile, setProfile] = useState<any>(null);
  const [pushStatus, setPushStatus] = useState<any>(null);
  const [editProfileOpen, setEditProfileOpen] = useState(false);
  const [pName, setPName] = useState("");
  const [pEmail, setPEmail] = useState("");
  const [pPhone, setPPhone] = useState("");
  const [pDob, setPDob] = useState("");
  const [pPps, setPPps] = useState("");
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
      const [r, b, h, w, a, e, m, ps] = await Promise.all([
        api.get("/holidays/requests"),
        api.get("/holidays/balance"),
        api.get("/clock/history"),
        api.get("/clock/weekly-summary").catch(() => ({ data: null })),
        api.get("/clock/accrual").catch(() => ({ data: null })),
        api.get("/users/me/eligibility").catch(() => ({ data: null })),
        api.get("/auth/me").catch(() => ({ data: null })),
        api.get("/users/me/push-status").catch(() => ({ data: null })),
      ]);
      setRequests(r.data);
      setBalance(b.data);
      setHistory(h.data.slice(0, 10));
      setWeekly(w.data);
      setAccrual(a.data);
      setEligibility(e.data);
      setProfile(m.data);
      setPushStatus(ps.data);
    } catch {}
  }, []);

  const openEditProfile = () => {
    const p = profile || user || {};
    setPName(p.name || "");
    setPEmail(p.email || "");
    setPPhone(p.phone || "");
    setPDob(p.dob || "");
    setPPps(p.pps_number || "");
    setEditProfileOpen(true);
  };

  const saveProfile = async () => {
    if (pDob && !/^\d{4}-\d{2}-\d{2}$/.test(pDob)) {
      return Alert.alert("Invalid DOB", "Use YYYY-MM-DD");
    }
    try {
      await api.patch("/users/me/profile", {
        name: pName || undefined,
        email: pEmail || undefined,
        phone: pPhone,
        dob: pDob,
        pps_number: pPps,
      });
      setEditProfileOpen(false);
      await load();
      Alert.alert("Saved", "Your profile has been updated.");
    } catch (e: any) {
      Alert.alert("Failed", e.response?.data?.detail || "Try again");
    }
  };

  const sendTestPush = async () => {
    try {
      const { data } = await api.post("/users/push-test", {
        title: "StaffHub test",
        body: "If you see this on your device, push delivery works ✅",
      });
      if (data.sent) {
        Alert.alert("Sent", "A test notification was dispatched. Check your device.");
      } else if (data.reason === "no_token") {
        Alert.alert(
          "Not registered",
          "Open the app on a real device and grant notification permission to register a push token.",
        );
      } else {
        Alert.alert("Failed", data.detail || "Push could not be sent.");
      }
      await load();
    } catch (e: any) {
      Alert.alert("Failed", e.response?.data?.detail || "Try again");
    }
  };

  const cancelRequest = (r: any) => {
    Alert.alert(
      "Cancel holiday?",
      `${r.start_date} → ${r.end_date}${r.days ? ` (${r.days} day${r.days === 1 ? "" : "s"})` : ""}. This will refund the days to your balance.`,
      [
        { text: "Keep request", style: "cancel" },
        {
          text: "Cancel it",
          style: "destructive",
          onPress: async () => {
            try {
              await api.post(`/holidays/requests/${r.id}/cancel`);
              await load();
            } catch (e: any) {
              Alert.alert("Failed", e.response?.data?.detail || "Try again");
            }
          },
        },
      ]
    );
  };

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
          <Text style={typography.h2}>{(profile?.name) || user?.name}</Text>
          <Text style={typography.small}>{(profile?.email) || user?.email}</Text>
          <View style={styles.rolePill}>
            <Feather
              name={user?.role === "admin" ? "shield" : "user"}
              size={12}
              color={colors.brand}
            />
            <Text style={styles.rolePillText}>{user?.role?.toUpperCase()}</Text>
          </View>
        </View>

        {/* Personal info card (editable) */}
        <View style={styles.section} testID="personal-info-card">
          <View style={styles.sectionHead}>
            <View style={{ flexDirection: "row", alignItems: "center" }}>
              <Feather name="user" size={16} color={colors.brand} />
              <Text style={[typography.label, { marginLeft: 6 }]}>Personal Info</Text>
            </View>
            <TouchableOpacity testID="edit-profile-btn" onPress={openEditProfile} style={styles.editLink}>
              <Feather name="edit-2" size={12} color={colors.brand} />
              <Text style={{ color: colors.brand, fontWeight: "700", fontSize: 12, marginLeft: 4 }}>Edit</Text>
            </TouchableOpacity>
          </View>
          <InfoRow icon="phone" label="Phone" value={profile?.phone} />
          <InfoRow icon="gift" label="Date of birth" value={profile?.dob} />
          <InfoRow icon="hash" label="PPS Number" value={profile?.pps_number} />
          <InfoRow icon="calendar" label="Start date" value={profile?.start_date} />
          <InfoRow
            icon="briefcase"
            label="Employment"
            value={profile?.employment_type ? profile.employment_type.replace("_", "-") : null}
          />
        </View>

        {/* Eligibility card — sick pay & bank holiday */}
        {eligibility && (
          <View style={styles.section} testID="eligibility-card">
            <View style={styles.sectionHead}>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <Feather name="check-circle" size={16} color={colors.brand} />
                <Text style={[typography.label, { marginLeft: 6 }]}>Eligibility</Text>
              </View>
              {eligibility.weeks_employed != null ? (
                <Text style={[typography.small, { color: colors.textMuted }]}>
                  {eligibility.weeks_employed}w employed
                </Text>
              ) : null}
            </View>
            <EligibilityRow
              ok={eligibility.sick_pay_eligible}
              icon="heart"
              label="Sick pay"
              detail={
                eligibility.sick_pay_eligible
                  ? "Eligible (≥13 continuous weeks)"
                  : eligibility.sick_pay_eligible_on
                  ? `Eligible on ${eligibility.sick_pay_eligible_on}`
                  : "Start date not set — ask admin"
              }
            />
            <EligibilityRow
              ok={eligibility.bank_holiday_eligible}
              icon="flag"
              label="Bank holiday"
              detail={
                eligibility.employment_type === "full_time"
                  ? "Full-time — immediate entitlement"
                  : eligibility.bank_holiday_eligible
                  ? `Part-time — ${eligibility.hours_last_5_weeks}h in last 5 weeks (≥40 required)`
                  : `Part-time — ${eligibility.hours_last_5_weeks}h in last 5 weeks (need ${eligibility.bank_holiday_threshold_hours}h)`
              }
            />
          </View>
        )}

        {/* Notifications / push status card */}
        {pushStatus && (
          <View style={styles.section} testID="push-card">
            <View style={styles.sectionHead}>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <Feather name="bell" size={16} color={colors.brand} />
                <Text style={[typography.label, { marginLeft: 6 }]}>Notifications</Text>
              </View>
              <View
                style={{
                  paddingHorizontal: 8,
                  paddingVertical: 4,
                  borderRadius: 999,
                  backgroundColor: pushStatus.registered ? "#DCFCE7" : colors.surface,
                }}
              >
                <Text
                  style={{
                    fontSize: 10,
                    fontWeight: "700",
                    color: pushStatus.registered ? colors.success : colors.textMuted,
                  }}
                >
                  {pushStatus.registered ? "REGISTERED" : "NOT REGISTERED"}
                </Text>
              </View>
            </View>
            {pushStatus.registered ? (
              <>
                <Text style={[typography.small, { color: colors.textMuted, fontSize: 11 }]}>
                  Push token: {pushStatus.token_preview}
                </Text>
                <TouchableOpacity
                  testID="send-test-push"
                  onPress={sendTestPush}
                  style={[styles.testPushBtn, { marginTop: 10 }]}
                >
                  <Feather name="send" size={14} color="#fff" />
                  <Text style={{ color: "#fff", fontWeight: "700", marginLeft: 6 }}>
                    Send Test Push
                  </Text>
                </TouchableOpacity>
              </>
            ) : (
              <Text style={[typography.small, { color: colors.textMuted }]}>
                {Platform.OS === "web"
                  ? "Push notifications work only on the iOS / Android app. Sign in on a real device and allow notifications to register your token."
                  : "Open the app on a real device and grant notification permission to register your token."}
              </Text>
            )}
          </View>
        )}

        {balance && (
          <>
            <View style={styles.row3}>
              <Stat label="Total" value={balance.entitlement} />
              <Stat label="Used" value={balance.used} color={colors.alert} />
              <Stat
                label={balance.in_deficit ? "Deficit" : "Left"}
                value={balance.remaining}
                color={balance.in_deficit ? colors.alert : colors.success}
              />
            </View>
            {balance.pending > 0 || balance.bank_holiday_count ? (
              <View style={styles.balanceMeta}>
                {balance.pending > 0 ? (
                  <Text style={[typography.small, { color: colors.brand, fontWeight: "600" }]}>
                    <Feather name="clock" size={11} color={colors.brand} />{" "}
                    {balance.pending} day{balance.pending === 1 ? "" : "s"} pending approval
                  </Text>
                ) : null}
                {balance.bank_holiday_count ? (
                  <Text style={[typography.small, { color: colors.textMuted }]}>
                    <Feather name="flag" size={11} color={colors.textMuted} />{" "}
                    {balance.bank_holiday_count} bank holiday{balance.bank_holiday_count === 1 ? "" : "s"} ({balance.bank_holiday_hours_value}h)
                  </Text>
                ) : null}
              </View>
            ) : null}
            {balance.in_deficit ? (
              <View style={styles.deficitBanner}>
                <Feather name="alert-triangle" size={14} color={colors.alert} />
                <Text style={[typography.small, { marginLeft: 6, color: colors.alert, flex: 1 }]}>
                  You're in deficit by {Math.abs(balance.remaining)} day{Math.abs(balance.remaining) === 1 ? "" : "s"}. New requests still allowed — admin will review.
                </Text>
              </View>
            ) : null}
          </>
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
            requests.map((r) => {
              const canCancel = r.status === "pending" || r.status === "approved";
              return (
                <View key={r.id} style={styles.requestRow} testID={`req-${r.id}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontWeight: "600", color: colors.primary }}>
                      {r.start_date} → {r.end_date}
                      {r.days ? (
                        <Text style={[typography.small, { color: colors.textMuted, fontWeight: "400" }]}>
                          {"  · "}
                          {r.days} day{r.days === 1 ? "" : "s"}
                        </Text>
                      ) : null}
                    </Text>
                    <Text style={typography.small}>
                      {r.type} {r.reason ? `· ${r.reason}` : ""}
                    </Text>
                    {r.status === "cancelled" && r.cancelled_by ? (
                      <Text style={[typography.small, { color: colors.textMuted, fontSize: 11 }]}>
                        Cancelled by {r.cancelled_by === "admin" ? r.cancelled_by_name || "admin" : "you"}
                      </Text>
                    ) : null}
                  </View>
                  <View style={{ alignItems: "flex-end" }}>
                    <View
                      style={[
                        styles.statusPill,
                        r.status === "approved" && { backgroundColor: "#D1FAE5" },
                        r.status === "rejected" && { backgroundColor: "#FEE2E2" },
                        r.status === "cancelled" && { backgroundColor: colors.surface },
                      ]}
                    >
                      <Text
                        style={[
                          styles.statusText,
                          r.status === "cancelled" && { color: colors.textMuted },
                        ]}
                      >
                        {r.status}
                      </Text>
                    </View>
                    {canCancel ? (
                      <TouchableOpacity
                        testID={`cancel-req-${r.id}`}
                        onPress={() => cancelRequest(r)}
                        style={styles.cancelLink}
                      >
                        <Feather name="x-circle" size={11} color={colors.alert} />
                        <Text
                          style={{ color: colors.alert, fontSize: 11, fontWeight: "600", marginLeft: 4 }}
                        >
                          Cancel
                        </Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                </View>
              );
            })
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

      {/* Edit profile modal */}
      <Modal
        visible={editProfileOpen}
        animationType="slide"
        transparent
        onRequestClose={() => setEditProfileOpen(false)}
      >
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <Text style={typography.h3}>Edit Profile</Text>
            <Text style={[typography.small, { color: colors.textMuted, marginBottom: 8 }]}>
              Personal details only visible to you and admins.
            </Text>
            <Text style={typography.label}>Name</Text>
            <TextInput
              testID="p-name"
              style={styles.input}
              value={pName}
              onChangeText={setPName}
              placeholderTextColor={colors.textMuted}
            />
            <Text style={[typography.label, { marginTop: 8 }]}>Email</Text>
            <TextInput
              testID="p-email"
              style={styles.input}
              value={pEmail}
              onChangeText={setPEmail}
              autoCapitalize="none"
              keyboardType="email-address"
              placeholderTextColor={colors.textMuted}
            />
            <Text style={[typography.label, { marginTop: 8 }]}>Phone</Text>
            <TextInput
              testID="p-phone"
              style={styles.input}
              value={pPhone}
              onChangeText={setPPhone}
              keyboardType="phone-pad"
              placeholder="+353 87 123 4567"
              placeholderTextColor={colors.textMuted}
            />
            <Text style={[typography.label, { marginTop: 8 }]}>Date of Birth</Text>
            <TextInput
              testID="p-dob"
              style={styles.input}
              value={pDob}
              onChangeText={setPDob}
              placeholder="YYYY-MM-DD"
              placeholderTextColor={colors.textMuted}
            />
            <Text style={[typography.label, { marginTop: 8 }]}>PPS Number</Text>
            <TextInput
              testID="p-pps"
              style={styles.input}
              value={pPps}
              onChangeText={setPPps}
              autoCapitalize="characters"
              placeholder="1234567T"
              placeholderTextColor={colors.textMuted}
            />
            <View style={{ flexDirection: "row", gap: 8, marginTop: 14 }}>
              <TouchableOpacity
                style={[styles.modalBtn, { backgroundColor: colors.surface }]}
                onPress={() => setEditProfileOpen(false)}
              >
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="p-save"
                style={[styles.modalBtn, { backgroundColor: colors.primary }]}
                onPress={saveProfile}
              >
                <Text style={{ color: "#fff", fontWeight: "700" }}>Save</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

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

function InfoRow({ icon, label, value }: { icon: any; label: string; value: any }) {
  return (
    <View style={styles.infoRow}>
      <View style={{ flexDirection: "row", alignItems: "center", flex: 1 }}>
        <Feather name={icon} size={13} color={colors.textMuted} />
        <Text style={[typography.small, { marginLeft: 8, color: colors.textMuted }]}>{label}</Text>
      </View>
      <Text
        style={{
          color: value ? colors.primary : colors.textMuted,
          fontWeight: value ? "600" : "400",
          fontSize: 13,
        }}
        numberOfLines={1}
      >
        {value || "—"}
      </Text>
    </View>
  );
}

function EligibilityRow({
  ok,
  icon,
  label,
  detail,
}: {
  ok: boolean;
  icon: any;
  label: string;
  detail: string;
}) {
  return (
    <View style={styles.infoRow}>
      <View style={{ flexDirection: "row", alignItems: "center", flex: 1 }}>
        <View
          style={[
            styles.elIcon,
            { backgroundColor: ok ? "#DCFCE7" : "#FEE2E2" },
          ]}
        >
          <Feather name={icon} size={12} color={ok ? colors.success : colors.alert} />
        </View>
        <View style={{ marginLeft: 10, flex: 1 }}>
          <Text style={{ fontWeight: "700", color: colors.primary, fontSize: 13 }}>{label}</Text>
          <Text style={[typography.small, { color: colors.textMuted, fontSize: 11 }]} numberOfLines={2}>
            {detail}
          </Text>
        </View>
      </View>
      <View
        style={{
          paddingHorizontal: 8,
          paddingVertical: 4,
          borderRadius: 999,
          backgroundColor: ok ? "#DCFCE7" : "#FEE2E2",
        }}
      >
        <Text style={{ fontSize: 10, fontWeight: "700", color: ok ? colors.success : colors.alert }}>
          {ok ? "ELIGIBLE" : "NOT YET"}
        </Text>
      </View>
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
  editLink: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 999,
    backgroundColor: colors.brandSoft,
  },
  infoRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 7,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  elIcon: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  balanceMeta: {
    flexDirection: "row",
    justifyContent: "space-between",
    flexWrap: "wrap",
    paddingHorizontal: 6,
    marginTop: 2,
    gap: 8,
  },
  deficitBanner: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#FEF3C7",
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: radius.md,
    marginTop: 6,
    borderWidth: 1,
    borderColor: "#FCD34D",
  },
  cancelLink: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 6,
    paddingVertical: 3,
    marginTop: 4,
  },
  testPushBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    height: 38,
    borderRadius: radius.pill,
    backgroundColor: colors.brand,
    alignSelf: "flex-start",
    paddingHorizontal: 16,
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
