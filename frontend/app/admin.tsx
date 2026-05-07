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
import { api } from "../src/api";
import { colors, spacing, radius, typography } from "../src/theme";

export default function AdminScreen() {
  const router = useRouter();
  const [tab, setTab] = useState<"holidays" | "shifts" | "forms" | "users">("holidays");
  const [holidays, setHolidays] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [allShifts, setAllShifts] = useState<any[]>([]);

  const [shiftModal, setShiftModal] = useState(false);
  const [sUser, setSUser] = useState("");
  const [sTitle, setSTitle] = useState("");
  const [sStart, setSStart] = useState("");
  const [sEnd, setSEnd] = useState("");
  const [sLoc, setSLoc] = useState("");

  const [formModal, setFormModal] = useState(false);
  const [fTitle, setFTitle] = useState("");
  const [fDesc, setFDesc] = useState("");
  const [fields, setFields] = useState<any[]>([
    { key: "name", label: "Full Name", type: "text", required: true },
  ]);

  const [userModal, setUserModal] = useState(false);
  const [uEmail, setUEmail] = useState("");
  const [uName, setUName] = useState("");
  const [uPass, setUPass] = useState("");
  const [uRole, setURole] = useState<"staff" | "admin">("staff");

  const load = useCallback(async () => {
    try {
      const [h, u, s] = await Promise.all([
        api.get("/holidays/requests", { params: { all: true } }),
        api.get("/users"),
        api.get("/shifts", { params: { all: true } }),
      ]);
      setHolidays(h.data);
      setUsers(u.data);
      setAllShifts(s.data);
    } catch {}
  }, []);

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
    if (!sUser || !sTitle || !sStart || !sEnd) {
      Alert.alert("Missing info", "All fields required");
      return;
    }
    try {
      await api.post("/shifts", {
        user_id: sUser,
        title: sTitle,
        start: sStart,
        end: sEnd,
        location: sLoc,
      });
      setShiftModal(false);
      setSUser(""); setSTitle(""); setSStart(""); setSEnd(""); setSLoc("");
      await load();
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Failed");
    }
  };

  const createForm = async () => {
    if (!fTitle || fields.length === 0) {
      Alert.alert("Missing info", "Title and at least one field required");
      return;
    }
    try {
      await api.post("/forms/templates", {
        title: fTitle,
        description: fDesc,
        fields,
      });
      setFormModal(false);
      setFTitle("");
      setFDesc("");
      setFields([{ key: "name", label: "Full Name", type: "text", required: true }]);
      await load();
      Alert.alert("Form Published", "Staff can now fill it out");
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Failed");
    }
  };

  const createUser = async () => {
    if (!uEmail || !uName || !uPass) {
      Alert.alert("Missing info");
      return;
    }
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
        {(["holidays", "shifts", "forms", "users"] as const).map((t) => (
          <TouchableOpacity
            key={t}
            onPress={() => setTab(t)}
            style={[styles.tab, tab === t && styles.tabActive]}
          >
            <Text style={[styles.tabText, tab === t && styles.tabTextActive]}>{t}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView contentContainerStyle={styles.list}>
        {tab === "holidays" &&
          holidays.map((h) => (
            <View key={h.id} style={styles.card}>
              <View style={{ flex: 1 }}>
                <Text style={{ fontWeight: "700", color: colors.primary }}>{h.user_name}</Text>
                <Text style={typography.small}>
                  {h.start_date} → {h.end_date} · {h.type}
                </Text>
                {h.reason ? <Text style={typography.small}>{h.reason}</Text> : null}
                <Text style={[typography.small, { marginTop: 4, fontWeight: "700" }]}>
                  {h.status?.toUpperCase()}
                </Text>
              </View>
              {h.status === "pending" && (
                <View style={{ gap: 6 }}>
                  <TouchableOpacity
                    style={[styles.smBtn, { backgroundColor: colors.success }]}
                    onPress={() => decideHoliday(h.id, "approved")}
                  >
                    <Feather name="check" size={14} color="#fff" />
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.smBtn, { backgroundColor: colors.alert }]}
                    onPress={() => decideHoliday(h.id, "rejected")}
                  >
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
                  <Text style={typography.small}>
                    {s.user_name} · {s.start?.slice(0, 16)} → {s.end?.slice(11, 16)}
                  </Text>
                </View>
                <TouchableOpacity
                  onPress={async () => {
                    await api.delete(`/shifts/${s.id}`);
                    await load();
                  }}
                >
                  <Feather name="trash-2" size={16} color={colors.alert} />
                </TouchableOpacity>
              </View>
            ))}
          </>
        )}

        {tab === "forms" && (
          <>
            <TouchableOpacity style={styles.addCta} onPress={() => setFormModal(true)}>
              <Feather name="plus" size={16} color="#fff" />
              <Text style={styles.addCtaText}>Create Form Template</Text>
            </TouchableOpacity>
            <Text style={[typography.small, { marginTop: 8 }]}>
              Build custom fillable forms with text, signature, checkbox, date, and dropdown fields.
            </Text>
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
                  <Text style={typography.small}>
                    {u.email} · {u.role}
                  </Text>
                </View>
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
              {users.filter(u => u.role === "staff").map((u) => (
                <TouchableOpacity key={u.id} style={[styles.userRow, sUser === u.id && styles.userRowActive]} onPress={() => setSUser(u.id)}>
                  <Text>{u.name}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
            <TextInput style={styles.input} placeholder="Title (e.g. Morning Shift)" value={sTitle} onChangeText={setSTitle} placeholderTextColor={colors.textMuted} />
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

      {/* Form Builder Modal */}
      <Modal visible={formModal} animationType="slide" onRequestClose={() => setFormModal(false)}>
        <SafeAreaView style={{ flex: 1, backgroundColor: "#fff" }}>
          <View style={styles.header}>
            <TouchableOpacity onPress={() => setFormModal(false)}>
              <Feather name="x" size={24} color={colors.primary} />
            </TouchableOpacity>
            <Text style={[typography.h3, { marginLeft: 12 }]}>New Form Template</Text>
          </View>
          <ScrollView contentContainerStyle={{ padding: spacing.lg }}>
            <TextInput style={styles.input} placeholder="Form Title" value={fTitle} onChangeText={setFTitle} placeholderTextColor={colors.textMuted} />
            <TextInput style={[styles.input, { height: 70 }]} placeholder="Description" value={fDesc} onChangeText={setFDesc} multiline placeholderTextColor={colors.textMuted} />
            <Text style={[typography.label, { marginTop: 16 }]}>Fields</Text>
            {fields.map((f, idx) => (
              <View key={idx} style={styles.fieldEditor}>
                <TextInput
                  style={[styles.input, { flex: 1 }]}
                  placeholder="Label"
                  value={f.label}
                  onChangeText={(v) => {
                    const c = [...fields];
                    c[idx].label = v;
                    c[idx].key = v.toLowerCase().replace(/\s+/g, "_") || `f${idx}`;
                    setFields(c);
                  }}
                />
                <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 4, marginTop: 6 }}>
                  {["text", "textarea", "date", "checkbox", "signature", "select", "number"].map((t) => (
                    <TouchableOpacity
                      key={t}
                      onPress={() => {
                        const c = [...fields];
                        c[idx].type = t;
                        setFields(c);
                      }}
                      style={[styles.typeChip, f.type === t && { backgroundColor: colors.primary }]}
                    >
                      <Text style={{ color: f.type === t ? "#fff" : colors.primary, fontSize: 11, fontWeight: "600" }}>
                        {t}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <TouchableOpacity
                  onPress={() => setFields(fields.filter((_, i) => i !== idx))}
                  style={{ alignSelf: "flex-end", marginTop: 4 }}
                >
                  <Text style={{ color: colors.alert, fontSize: 12, fontWeight: "700" }}>REMOVE</Text>
                </TouchableOpacity>
              </View>
            ))}
            <TouchableOpacity
              style={[styles.modalBtn, { backgroundColor: colors.surface, marginTop: 8 }]}
              onPress={() =>
                setFields([
                  ...fields,
                  { key: `f${fields.length}`, label: "New Field", type: "text", required: false },
                ])
              }
            >
              <Text style={{ color: colors.primary, fontWeight: "700" }}>+ Add Field</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.modalBtn, { backgroundColor: colors.primary, marginTop: 12 }]}
              onPress={createForm}
            >
              <Text style={{ color: "#fff", fontWeight: "700" }}>Publish Form</Text>
            </TouchableOpacity>
          </ScrollView>
        </SafeAreaView>
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
                <TouchableOpacity
                  key={r}
                  style={[styles.typeChip, uRole === r && { backgroundColor: colors.primary }]}
                  onPress={() => setURole(r)}
                >
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
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.md,
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
  },
  tabs: { flexDirection: "row", padding: spacing.md, gap: 6, flexWrap: "wrap" },
  tab: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.pill, backgroundColor: colors.surface },
  tabActive: { backgroundColor: colors.primary },
  tabText: { color: colors.textSecondary, fontWeight: "600", fontSize: 13, textTransform: "capitalize" },
  tabTextActive: { color: "#fff" },
  list: { padding: spacing.lg, gap: spacing.sm },
  card: {
    backgroundColor: "#fff",
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  smBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  addCta: {
    flexDirection: "row",
    height: 48,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
  },
  addCtaText: { color: "#fff", fontWeight: "700" },
  modalBg: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.4)" },
  modalCard: { backgroundColor: "#fff", padding: spacing.lg, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl },
  input: {
    height: 48,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    marginTop: spacing.sm,
    color: colors.textPrimary,
  },
  modalBtn: { flex: 1, height: 48, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  userRow: { padding: 10, borderRadius: radius.md, backgroundColor: colors.surface, marginBottom: 4 },
  userRowActive: { backgroundColor: colors.brandSoft, borderWidth: 1, borderColor: colors.brand },
  typeChip: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
  },
  fieldEditor: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: 10,
    marginTop: 6,
  },
});
