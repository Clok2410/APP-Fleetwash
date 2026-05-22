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
import { useFocusEffect, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { SafeAreaView } from "react-native-safe-area-context";
import { Calendar } from "react-native-calendars";
import { api } from "../../src/api";
import { useAuth } from "../../src/auth";
import { colors, spacing, radius, typography } from "../../src/theme";
import CustomerModal from "../../src/components/CustomerModal";
import * as Linking from "expo-linking";
import { Platform } from "react-native";

export default function ScheduleScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const [shifts, setShifts] = useState<any[]>([]);
  const [swaps, setSwaps] = useState<any[]>([]);
  const [availability, setAvailability] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [tab, setTab] = useState<"shifts" | "swaps" | "availability">("shifts");
  const [swapModal, setSwapModal] = useState<{ shiftId: string } | null>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [swapTarget, setSwapTarget] = useState<string>("");
  const [swapReason, setSwapReason] = useState("");
  const [activeCustomerId, setActiveCustomerId] = useState<string | null>(null);
  const [pinnedNotes, setPinnedNotes] = useState<Record<string, any[]>>({});
  const [availDate, setAvailDate] = useState<string>("");
  const [availNote, setAvailNote] = useState<string>("");
  const [latestRoster, setLatestRoster] = useState<any>(null);

  const load = useCallback(async () => {
    try {
      const [s, sw, u, av] = await Promise.all([
        api.get("/shifts"),
        api.get("/shifts/swaps"),
        api.get("/users"),
        api.get("/availability"),
      ]);
      setShifts(s.data);
      setSwaps(sw.data);
      setUsers(u.data.filter((x: any) => x.id !== user?.id && x.role === "staff"));
      setAvailability(av.data || []);
      // Latest published roster PDF (separate try because 404 is normal when none published)
      try {
        const { data: r } = await api.get("/published-rosters/latest");
        setLatestRoster(r);
      } catch {
        setLatestRoster(null);
      }
      // Fetch pinned notes for each unique customer linked to a shift
      const cIds = Array.from(new Set((s.data || []).map((x: any) => x.customer_id).filter(Boolean)));
      const noteMap: Record<string, any[]> = {};
      await Promise.all(
        cIds.map(async (cid: any) => {
          try {
            const { data } = await api.get(`/customers/${cid}/notes`);
            noteMap[cid] = (data || []).filter((n: any) => n.pinned);
          } catch {}
        })
      );
      setPinnedNotes(noteMap);
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

      {latestRoster && (
        <TouchableOpacity
          testID="latest-roster-card"
          activeOpacity={0.85}
          onPress={async () => {
            try {
              const baseUrl = (process.env.EXPO_PUBLIC_BACKEND_URL || "").replace(/\/$/, "");
              const token = (await import("@react-native-async-storage/async-storage")).default;
              const t = await token.getItem("access_token");
              const url = `${baseUrl}/api/published-rosters/${latestRoster.id}/pdf`;
              if (Platform.OS === "web") {
                // Fetch with token, open as blob in new tab
                const res = await fetch(url, { headers: { Authorization: `Bearer ${t}` } });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const blob = await res.blob();
                const objectUrl = URL.createObjectURL(blob);
                window.open(objectUrl, "_blank");
              } else {
                // Mobile: open in browser; backend uses Bearer auth so we need a workaround.
                // Easiest: ask the system browser to open the PDF via an authed deep-link.
                // Quick approach: fetch into a local file, then share.
                const FileSystem = await import("expo-file-system");
                const Sharing = await import("expo-sharing");
                const local = FileSystem.cacheDirectory + `roster-${latestRoster.id}.pdf`;
                const dl = await FileSystem.downloadAsync(url, local, {
                  headers: { Authorization: `Bearer ${t}` },
                });
                if (dl.status === 200) {
                  if (await Sharing.isAvailableAsync()) {
                    await Sharing.shareAsync(dl.uri, { mimeType: "application/pdf" });
                  } else {
                    Alert.alert("Downloaded", `PDF saved to: ${dl.uri}`);
                  }
                } else {
                  throw new Error(`HTTP ${dl.status}`);
                }
              }
            } catch (e: any) {
              Alert.alert("Couldn't open PDF", String(e?.message || e));
            }
          }}
          style={styles.rosterCard}
        >
          <View style={styles.rosterIcon}>
            <Feather name="file-text" size={20} color="#fff" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={typography.label}>This Week's Roster</Text>
            <Text style={styles.rosterTitle} numberOfLines={1}>{latestRoster.title}</Text>
            <Text style={styles.rosterMeta}>
              Published by {latestRoster.published_by_name || "Admin"}
              {latestRoster.published_at ? ` · ${latestRoster.published_at.slice(0, 10)}` : ""}
            </Text>
          </View>
          <Feather name="download" size={20} color={colors.success} />
        </TouchableOpacity>
      )}

      {user?.role === "admin" && (
        <TouchableOpacity
          testID="ai-roster-import-banner"
          activeOpacity={0.85}
          onPress={() => router.push("/admin?openRoster=1")}
          style={styles.aiBanner}
        >
          <View style={styles.aiBannerIcon}>
            <Feather name="zap" size={18} color="#fff" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.aiBannerTitle}>Import roster from PDF</Text>
            <Text style={styles.aiBannerSub}>
              Claude Sonnet 4.5 parses your Google Sheets roster into shifts in seconds.
            </Text>
          </View>
          <Feather name="arrow-right" size={20} color={colors.primary} />
        </TouchableOpacity>
      )}

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
        <TouchableOpacity
          testID="tab-availability"
          onPress={() => setTab("availability")}
          style={[styles.tab, tab === "availability" && styles.tabActive]}
        >
          <Text style={[styles.tabText, tab === "availability" && styles.tabTextActive]}>
            Availability
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
            shifts.map((s) => {
              const notes = (s.customer_id && pinnedNotes[s.customer_id]) || [];
              return (
                <View key={s.id} style={styles.shiftCard} testID={`shift-${s.id}`}>
                  <View style={styles.shiftLeft}>
                    <Text style={typography.label}>{s.start?.slice(0, 10)}</Text>
                    <Text style={[typography.h3, { marginTop: 4 }]}>{s.title}</Text>
                    <Text style={typography.small}>
                      {s.start?.slice(11, 16)} – {s.end?.slice(11, 16)} · {s.location || "—"}
                    </Text>
                    {s.customer_name ? (
                      <View style={styles.customerRow}>
                        <Feather name="briefcase" size={13} color={colors.primary} />
                        <Text style={[typography.small, { marginLeft: 6, fontWeight: "600", color: colors.primary }]}>
                          {s.customer_name}
                          {s.site_name ? ` · ${s.site_name}` : ""}
                        </Text>
                      </View>
                    ) : null}
                    {s.notes ? (
                      <Text style={[typography.small, { marginTop: 4 }]}>{s.notes}</Text>
                    ) : null}
                    {notes.length > 0 ? (
                      <View style={{ marginTop: 6 }}>
                        {notes.slice(0, 2).map((n: any) => (
                          <View key={n.id} style={styles.pinnedNote}>
                            <Feather name="bookmark" size={12} color="#92400E" />
                            <Text
                              style={[typography.small, { marginLeft: 6, flex: 1, color: "#78350F" }]}
                              numberOfLines={2}
                            >
                              {n.body || n.content}
                            </Text>
                          </View>
                        ))}
                      </View>
                    ) : null}
                    {s.customer_id ? (
                      <TouchableOpacity
                        testID={`view-cust-${s.id}`}
                        style={styles.viewCustBtn}
                        onPress={() => setActiveCustomerId(s.customer_id)}
                      >
                        <Feather name="user" size={12} color="#fff" />
                        <Text style={{ color: "#fff", fontWeight: "700", marginLeft: 6, fontSize: 12 }}>
                          View Customer
                        </Text>
                      </TouchableOpacity>
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
              );
            })
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

        {tab === "availability" && (
          <>
            <Text style={[typography.small, { marginBottom: 8 }]}>
              Tap a date below to mark yourself unavailable. Tap again to clear.
            </Text>
            <View style={{ borderRadius: radius.lg, overflow: "hidden", borderWidth: 1, borderColor: colors.border }}>
              <Calendar
                testID="availability-calendar"
                onDayPress={(d: any) => {
                  setAvailDate(d.dateString);
                }}
                markedDates={(() => {
                  const m: any = {};
                  availability.forEach((a) => {
                    if (!a.available) {
                      m[a.date] = { selected: true, selectedColor: colors.alert };
                    }
                  });
                  if (availDate) {
                    m[availDate] = {
                      ...(m[availDate] || {}),
                      selected: true,
                      selectedColor: m[availDate]?.selectedColor || colors.primary,
                      marked: true,
                    };
                  }
                  return m;
                })()}
                theme={{
                  todayTextColor: colors.brand,
                  arrowColor: colors.primary,
                  selectedDayBackgroundColor: colors.primary,
                }}
              />
            </View>
            {availDate ? (
              <View style={{ marginTop: 12 }}>
                <Text style={typography.label}>Selected: {availDate}</Text>
                <TextInput
                  testID="availability-note"
                  style={styles.input}
                  placeholder="Reason (optional, e.g. medical, family)"
                  value={availNote}
                  onChangeText={setAvailNote}
                  placeholderTextColor={colors.textMuted}
                />
                <View style={{ flexDirection: "row", gap: 8, marginTop: 10 }}>
                  <TouchableOpacity
                    testID="availability-mark-off"
                    style={[styles.btn, { backgroundColor: colors.alert }]}
                    onPress={async () => {
                      try {
                        await api.post("/availability", {
                          date: availDate,
                          available: false,
                          note: availNote || undefined,
                        });
                        setAvailNote("");
                        setAvailDate("");
                        await load();
                      } catch (e: any) {
                        Alert.alert("Error", e.response?.data?.detail || "Failed");
                      }
                    }}
                  >
                    <Text style={styles.btnPrimaryText}>Mark Unavailable</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    testID="availability-mark-on"
                    style={[styles.btn, { backgroundColor: colors.success }]}
                    onPress={async () => {
                      try {
                        await api.post("/availability", {
                          date: availDate,
                          available: true,
                          note: undefined,
                        });
                        setAvailNote("");
                        setAvailDate("");
                        await load();
                      } catch (e: any) {
                        Alert.alert("Error", e.response?.data?.detail || "Failed");
                      }
                    }}
                  >
                    <Text style={styles.btnPrimaryText}>Mark Available</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ) : null}
            {availability.filter((a) => !a.available).length > 0 && (
              <View style={{ marginTop: 16 }}>
                <Text style={typography.label}>Your unavailable days</Text>
                {availability.filter((a) => !a.available).map((a, i) => (
                  <View key={i} style={[styles.shiftCard, { paddingVertical: 8 }]}>
                    <View style={styles.shiftLeft}>
                      <Text style={[typography.small, { fontWeight: "700", color: colors.primary }]}>{a.date}</Text>
                      {a.note ? <Text style={typography.small}>{a.note}</Text> : null}
                    </View>
                  </View>
                ))}
              </View>
            )}
          </>
        )}
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
      <CustomerModal customerId={activeCustomerId} onClose={() => setActiveCustomerId(null)} />
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
  rosterCard: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    padding: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: colors.success,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  rosterIcon: {
    width: 38,
    height: 38,
    borderRadius: radius.md,
    backgroundColor: colors.success,
    alignItems: "center",
    justifyContent: "center",
  },
  rosterTitle: { fontSize: 15, fontWeight: "700", color: colors.textPrimary, marginTop: 2 },
  rosterMeta: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  aiBanner: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    padding: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.brandSoft,
    borderWidth: 1,
    borderColor: colors.primary,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  aiBannerIcon: {
    width: 34,
    height: 34,
    borderRadius: radius.md,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  aiBannerTitle: { fontSize: 15, fontWeight: "700", color: colors.textPrimary },
  aiBannerSub: { fontSize: 12, color: colors.textSecondary, marginTop: 2 },
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
  customerRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 6,
  },
  pinnedNote: {
    flexDirection: "row",
    alignItems: "flex-start",
    backgroundColor: "#FEF3C7",
    borderRadius: radius.sm,
    padding: 6,
    marginTop: 4,
  },
  viewCustBtn: {
    alignSelf: "flex-start",
    marginTop: 8,
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.brand,
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
