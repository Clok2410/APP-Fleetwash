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
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { SafeAreaView } from "react-native-safe-area-context";
import { Linking, Platform } from "react-native";
import { api } from "../src/api";
import { colors, spacing, radius, typography } from "../src/theme";
import FormBuilderModal from "../src/components/FormBuilderModal";
import StatsModal from "../src/components/StatsModal";

export default function AdminScreen() {
  const router = useRouter();
  const [tab, setTab] = useState<"holidays" | "shifts" | "forms" | "users" | "depots" | "offsite">("holidays");
  const [holidays, setHolidays] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [allShifts, setAllShifts] = useState<any[]>([]);
  const [allTemplates, setAllTemplates] = useState<any[]>([]);
  const [depots, setDepots] = useState<any[]>([]);
  const [offsite, setOffsite] = useState<any[]>([]);
  const [depotModal, setDepotModal] = useState(false);
  const [dName, setDName] = useState("");
  const [dLat, setDLat] = useState("");
  const [dLng, setDLng] = useState("");
  const [dRadius, setDRadius] = useState("200");
  const [digestBusy, setDigestBusy] = useState(false);

  const [shiftModal, setShiftModal] = useState(false);
  const [sUser, setSUser] = useState("");
  const [sTitle, setSTitle] = useState("");
  const [sStart, setSStart] = useState("");
  const [sEnd, setSEnd] = useState("");
  const [sLoc, setSLoc] = useState("");

  const [formModal, setFormModal] = useState(false);
  const [statsTpl, setStatsTpl] = useState<any>(null);

  const [userModal, setUserModal] = useState(false);
  const [uEmail, setUEmail] = useState("");
  const [uName, setUName] = useState("");
  const [uPass, setUPass] = useState("");
  const [uRole, setURole] = useState<"staff" | "admin">("staff");

  const load = useCallback(async () => {
    try {
      const [h, u, s, t, d, o] = await Promise.all([
        api.get("/holidays/requests", { params: { all: true } }),
        api.get("/users"),
        api.get("/shifts", { params: { all: true } }),
        api.get("/forms/templates"),
        api.get("/depots"),
        api.get("/admin/off-site-clock-ins").catch(() => ({ data: [] })),
      ]);
      setHolidays(h.data);
      setUsers(u.data);
      setAllShifts(s.data);
      setAllTemplates(t.data);
      setDepots(d.data);
      setOffsite(o.data || []);
    } catch {}
  }, []);

  const openInMaps = (lat: number, lng: number) => {
    const url = Platform.select({
      ios: `https://maps.apple.com/?ll=${lat},${lng}&q=Off-site`,
      default: `https://www.google.com/maps?q=${lat},${lng}`,
    })!;
    Linking.openURL(url);
  };

  const createDepot = async () => {
    if (!dName || !dLat || !dLng) return Alert.alert("Missing info");
    try {
      await api.post("/depots", {
        name: dName,
        lat: parseFloat(dLat),
        lng: parseFloat(dLng),
        radius_m: parseFloat(dRadius) || 200,
      });
      setDepotModal(false);
      setDName(""); setDLat(""); setDLng(""); setDRadius("200");
      await load();
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Failed");
    }
  };

  const sendDigest = async () => {
    setDigestBusy(true);
    try {
      const { data } = await api.post("/admin/weekly-digest");
      Alert.alert(
        "Digest generated",
        `${data.mocked ? "MOCKED — no API key set." : "Sent."} Recipients: ${(data.recipients || []).join(", ")}\nFile: ${data.filename}`
      );
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Failed");
    } finally {
      setDigestBusy(false);
    }
  };

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const decideHoliday = async (id: string, decision: string) => {
    await api.post(`/holidays/requests/${id}/decision`, null, { params: { decision } });
    await load();
  };

  const createShift = async () => {
    if (!sUser || !sTitle || !sStart || !sEnd) return Alert.alert("Missing info", "All fields required");
    try {
      await api.post("/shifts", { user_id: sUser, title: sTitle, start: sStart, end: sEnd, location: sLoc });
      setShiftModal(false);
      setSUser(""); setSTitle(""); setSStart(""); setSEnd(""); setSLoc("");
      await load();
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Failed");
    }
  };

  const createUser = async () => {
    if (!uEmail || !uName || !uPass) return Alert.alert("Missing info");
    try {
      await api.post("/auth/register", { email: uEmail, name: uName, password: uPass, role: uRole });
      setUserModal(false);
      setUEmail(""); setUName(""); setUPass(""); setURole("staff");
      await load();
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Failed");
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Feather name="x" size={24} color={colors.primary} />
        </TouchableOpacity>
        <Text style={[typography.h3, { marginLeft: 12 }]}>Admin Panel</Text>
      </View>

      <View style={styles.tabs}>
        {(["holidays", "shifts", "forms", "users", "depots", "offsite"] as const).map((t) => (
          <TouchableOpacity
            key={t}
            testID={`admin-tab-${t}`}
            onPress={() => setTab(t)}
            style={[styles.tab, tab === t && styles.tabActive]}
          >
            <Text style={[styles.tabText, tab === t && styles.tabTextActive]}>
              {t === "offsite" ? `off-site${offsite.length ? ` · ${offsite.length}` : ""}` : t}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView contentContainerStyle={styles.list}>
        {tab === "holidays" &&
          holidays.map((h) => (
            <View key={h.id} style={styles.card}>
              <View style={{ flex: 1 }}>
                <Text style={{ fontWeight: "700", color: colors.primary }}>{h.user_name}</Text>
                <Text style={typography.small}>{h.start_date} → {h.end_date} · {h.type}</Text>
                {h.reason ? <Text style={typography.small}>{h.reason}</Text> : null}
                <Text style={[typography.small, { marginTop: 4, fontWeight: "700" }]}>{h.status?.toUpperCase()}</Text>
              </View>
              {h.status === "pending" && (
                <View style={{ gap: 6 }}>
                  <TouchableOpacity style={[styles.smBtn, { backgroundColor: colors.success }]} onPress={() => decideHoliday(h.id, "approved")}>
                    <Feather name="check" size={14} color="#fff" />
                  </TouchableOpacity>
                  <TouchableOpacity style={[styles.smBtn, { backgroundColor: colors.alert }]} onPress={() => decideHoliday(h.id, "rejected")}>
                    <Feather name="x" size={14} color="#fff" />
                  </TouchableOpacity>
                </View>
              )}
            </View>
          ))}

        {tab === "shifts" && (
          <>
            <TouchableOpacity style={styles.addCta} onPress={() => setShiftModal(true)}>
              <Feather name="plus" size={16} color="#fff" />
              <Text style={styles.addCtaText}>Assign New Shift</Text>
            </TouchableOpacity>
            {allShifts.map((s) => (
              <View key={s.id} style={styles.card}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontWeight: "700", color: colors.primary }}>{s.title}</Text>
                  <Text style={typography.small}>{s.user_name} · {s.start?.slice(0, 16)} → {s.end?.slice(11, 16)}</Text>
                </View>
                <TouchableOpacity onPress={async () => { await api.delete(`/shifts/${s.id}`); await load(); }}>
                  <Feather name="trash-2" size={16} color={colors.alert} />
                </TouchableOpacity>
              </View>
            ))}
          </>
        )}

        {tab === "forms" && (
          <>
            <TouchableOpacity testID="open-form-builder" style={styles.addCta} onPress={() => setFormModal(true)}>
              <Feather name="plus" size={16} color="#fff" />
              <Text style={styles.addCtaText}>Create Form / Checklist</Text>
            </TouchableOpacity>
            <Text style={[typography.small, { marginTop: 8, marginBottom: 4 }]}>
              Build forms or daily checklists (e.g. truck wash). Tap Stats on a checklist to see washed/missed analytics.
            </Text>
            {allTemplates.map((t) => (
              <View key={t.id} style={styles.card} testID={`tpl-${t.id}`}>
                <View style={[styles.smBtn, { backgroundColor: t.kind === "checklist" ? colors.brand : colors.surface, width: 36, height: 36, borderRadius: 18 }]}>
                  <Feather name={t.kind === "checklist" ? "check-square" : "file-text"} size={16} color={t.kind === "checklist" ? "#fff" : colors.primary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontWeight: "700", color: colors.primary }}>{t.title}</Text>
                  <Text style={typography.small}>
                    {t.kind === "checklist"
                      ? `${(t.checklist_items || []).length} items · target ${t.target_percent || 100}%`
                      : `${(t.fields || []).length} fields`}
                  </Text>
                </View>
                {t.kind === "checklist" && (
                  <TouchableOpacity
                    testID={`stats-${t.id}`}
                    style={[styles.smBtn, { backgroundColor: colors.brand, width: 64, borderRadius: 14 }]}
                    onPress={() => setStatsTpl(t)}
                  >
                    <Feather name="bar-chart-2" size={14} color="#fff" />
                    <Text style={{ color: "#fff", fontSize: 11, fontWeight: "700", marginLeft: 4 }}>Stats</Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity onPress={async () => { await api.delete(`/forms/templates/${t.id}`); await load(); }} style={{ marginLeft: 8 }}>
                  <Feather name="trash-2" size={14} color={colors.alert} />
                </TouchableOpacity>
              </View>
            ))}
          </>
        )}

        {tab === "users" && (
          <>
            <TouchableOpacity style={styles.addCta} onPress={() => setUserModal(true)}>
              <Feather name="user-plus" size={16} color="#fff" />
              <Text style={styles.addCtaText}>Add Employee</Text>
            </TouchableOpacity>
            {users.map((u) => (
              <View key={u.id} style={styles.card}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontWeight: "700", color: colors.primary }}>{u.name}</Text>
                  <Text style={typography.small}>{u.email} · {u.role}</Text>
                </View>
              </View>
            ))}
          </>
        )}

        {tab === "depots" && (
          <>
            <TouchableOpacity testID="open-depot-modal" style={styles.addCta} onPress={() => setDepotModal(true)}>
              <Feather name="map-pin" size={16} color="#fff" />
              <Text style={styles.addCtaText}>Add Depot</Text>
            </TouchableOpacity>
            <Text style={[typography.small, { marginTop: 8, marginBottom: 4 }]}>
              Geofences: clock-ins outside any depot's radius are flagged "off-site" and notify all admins.
            </Text>
            <TouchableOpacity
              testID="send-digest-btn"
              style={[styles.addCta, { backgroundColor: colors.brand, marginTop: 4 }]}
              onPress={sendDigest}
              disabled={digestBusy}
            >
              <Feather name="mail" size={16} color="#fff" />
              <Text style={styles.addCtaText}>{digestBusy ? "Generating…" : "Send Weekly Digest Now"}</Text>
            </TouchableOpacity>
            {depots.map((d) => (
              <View key={d.id} style={styles.card} testID={`depot-${d.id}`}>
                <View style={[styles.smBtn, { backgroundColor: colors.brandSoft, width: 36, height: 36, borderRadius: 18 }]}>
                  <Feather name="map-pin" size={16} color={colors.brand} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontWeight: "700", color: colors.primary }}>{d.name}</Text>
                  <Text style={typography.small}>
                    {d.lat?.toFixed(4)}, {d.lng?.toFixed(4)} · {d.radius_m}m radius
                  </Text>
                </View>
                <TouchableOpacity onPress={async () => { await api.delete(`/depots/${d.id}`); await load(); }}>
                  <Feather name="trash-2" size={14} color={colors.alert} />
                </TouchableOpacity>
              </View>
            ))}
          </>
        )}
      </ScrollView>

      {/* Shift Modal */}
      <Modal visible={shiftModal} animationType="slide" transparent onRequestClose={() => setShiftModal(false)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <Text style={typography.h3}>Assign Shift</Text>
            <ScrollView style={{ maxHeight: 140, marginTop: 8 }}>
              {users.filter((u) => u.role === "staff").map((u) => (
                <TouchableOpacity key={u.id} style={[styles.userRow, sUser === u.id && styles.userRowActive]} onPress={() => setSUser(u.id)}>
                  <Text>{u.name}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
            <TextInput style={styles.input} placeholder="Title" value={sTitle} onChangeText={setSTitle} placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="Start (YYYY-MM-DDTHH:MM)" value={sStart} onChangeText={setSStart} placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="End (YYYY-MM-DDTHH:MM)" value={sEnd} onChangeText={setSEnd} placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="Location" value={sLoc} onChangeText={setSLoc} placeholderTextColor={colors.textMuted} />
            <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
              <TouchableOpacity style={[styles.modalBtn, { backgroundColor: colors.surface }]} onPress={() => setShiftModal(false)}>
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.modalBtn, { backgroundColor: colors.primary }]} onPress={createShift}>
                <Text style={{ color: "#fff", fontWeight: "700" }}>Assign</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* User Modal */}
      <Modal visible={userModal} animationType="slide" transparent onRequestClose={() => setUserModal(false)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <Text style={typography.h3}>New Employee</Text>
            <TextInput style={styles.input} placeholder="Name" value={uName} onChangeText={setUName} placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="Email" value={uEmail} onChangeText={setUEmail} autoCapitalize="none" placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="Initial Password" value={uPass} onChangeText={setUPass} secureTextEntry placeholderTextColor={colors.textMuted} />
            <View style={{ flexDirection: "row", gap: 8, marginTop: 8 }}>
              {(["staff", "admin"] as const).map((r) => (
                <TouchableOpacity key={r} style={[styles.typeChip, uRole === r && { backgroundColor: colors.primary }]} onPress={() => setURole(r)}>
                  <Text style={{ color: uRole === r ? "#fff" : colors.primary, fontWeight: "600" }}>{r}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
              <TouchableOpacity style={[styles.modalBtn, { backgroundColor: colors.surface }]} onPress={() => setUserModal(false)}>
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.modalBtn, { backgroundColor: colors.primary }]} onPress={createUser}>
                <Text style={{ color: "#fff", fontWeight: "700" }}>Create</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      <FormBuilderModal visible={formModal} onClose={() => setFormModal(false)} onPublished={load} depots={depots} />
      <StatsModal template={statsTpl} onClose={() => setStatsTpl(null)} />

      {/* Depot Modal */}
      <Modal visible={depotModal} animationType="slide" transparent onRequestClose={() => setDepotModal(false)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <Text style={typography.h3}>Add Depot</Text>
            <TextInput style={styles.input} placeholder="Name (e.g. Dublin HQ)" value={dName} onChangeText={setDName} placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="Latitude (e.g. 53.3498)" value={dLat} onChangeText={setDLat} keyboardType="numeric" placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="Longitude (e.g. -6.2603)" value={dLng} onChangeText={setDLng} keyboardType="numeric" placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="Radius in metres (default 200)" value={dRadius} onChangeText={setDRadius} keyboardType="numeric" placeholderTextColor={colors.textMuted} />
            <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
              <TouchableOpacity style={[styles.modalBtn, { backgroundColor: colors.surface }]} onPress={() => setDepotModal(false)}>
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="create-depot-submit" style={[styles.modalBtn, { backgroundColor: colors.primary }]} onPress={createDepot}>
                <Text style={{ color: "#fff", fontWeight: "700" }}>Add</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: "row", alignItems: "center", padding: spacing.md, borderBottomColor: colors.border, borderBottomWidth: 1 },
  tabs: { flexDirection: "row", padding: spacing.md, gap: 6, flexWrap: "wrap" },
  tab: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.pill, backgroundColor: colors.surface },
  tabActive: { backgroundColor: colors.primary },
  tabText: { color: colors.textSecondary, fontWeight: "600", fontSize: 13, textTransform: "capitalize" },
  tabTextActive: { color: "#fff" },
  list: { padding: spacing.lg, gap: spacing.sm },
  card: { backgroundColor: "#fff", borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: 14, flexDirection: "row", alignItems: "center", gap: 12 },
  smBtn: { width: 32, height: 32, borderRadius: 16, alignItems: "center", justifyContent: "center", flexDirection: "row" },
  addCta: { flexDirection: "row", height: 48, borderRadius: radius.pill, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center", gap: 6 },
  addCtaText: { color: "#fff", fontWeight: "700" },
  modalBg: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.4)" },
  modalCard: { backgroundColor: "#fff", padding: spacing.lg, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl },
  input: { height: 48, backgroundColor: colors.surface, borderRadius: radius.md, paddingHorizontal: spacing.md, marginTop: spacing.sm, color: colors.textPrimary },
  modalBtn: { flex: 1, height: 48, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  userRow: { padding: 10, borderRadius: radius.md, backgroundColor: colors.surface, marginBottom: 4 },
  userRowActive: { backgroundColor: colors.brandSoft, borderWidth: 1, borderColor: colors.brand },
  typeChip: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill, backgroundColor: colors.surface },
});
