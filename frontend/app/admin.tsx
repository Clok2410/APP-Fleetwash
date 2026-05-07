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
  const [fKind, setFKind] = useState<"form" | "checklist">("form");
  const [fTarget, setFTarget] = useState("100");
  const [subKeysInput, setSubKeysInput] = useState("EXT,INT");
  const [items, setItems] = useState<any[]>([
    { id: "HL29", label: "HL 29", sub_keys: ["EXT", "INT"] },
    { id: "HL30", label: "HL 30", sub_keys: ["EXT", "INT"] },
  ]);
  const [bulkInput, setBulkInput] = useState("");
  const [allTemplates, setAllTemplates] = useState<any[]>([]);
  const [statsTpl, setStatsTpl] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [statsBusy, setStatsBusy] = useState(false);
  const [statsRange, setStatsRange] = useState<"day" | "week" | "month" | "all">("month");

  const [userModal, setUserModal] = useState(false);
  const [uEmail, setUEmail] = useState("");
  const [uName, setUName] = useState("");
  const [uPass, setUPass] = useState("");
  const [uRole, setURole] = useState<"staff" | "admin">("staff");

  const load = useCallback(async () => {
    try {
      const [h, u, s, t] = await Promise.all([
        api.get("/holidays/requests", { params: { all: true } }),
        api.get("/users"),
        api.get("/shifts", { params: { all: true } }),
        api.get("/forms/templates"),
      ]);
      setHolidays(h.data);
      setUsers(u.data);
      setAllShifts(s.data);
      setAllTemplates(t.data);
    } catch {}
  }, []);

  const openStats = async (tpl: any, range: "day" | "week" | "month" | "all" = "month") => {
    setStatsTpl(tpl);
    setStatsRange(range);
    setStats(null);
    setStatsBusy(true);
    try {
      const params: any = {};
      const now = new Date();
      if (range === "day") {
        params.date_from = now.toISOString().slice(0, 10);
      } else if (range === "week") {
        const from = new Date(now); from.setDate(from.getDate() - 7);
        params.date_from = from.toISOString().slice(0, 10);
      } else if (range === "month") {
        const from = new Date(now); from.setMonth(from.getMonth() - 1);
        params.date_from = from.toISOString().slice(0, 10);
      }
      const { data } = await api.get(`/forms/templates/${tpl.id}/stats`, { params });
      setStats(data);
    } catch (e: any) {
      Alert.alert("Stats failed", e.response?.data?.detail || "Failed");
    } finally {
      setStatsBusy(false);
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
    if (!fTitle) {
      Alert.alert("Missing info", "Title required");
      return;
    }
    if (fKind === "form" && fields.length === 0) {
      Alert.alert("Missing info", "Add at least one field");
      return;
    }
    if (fKind === "checklist" && items.length === 0) {
      Alert.alert("Missing info", "Add at least one checklist item");
      return;
    }
    try {
      const payload: any = {
        title: fTitle,
        description: fDesc,
        kind: fKind,
        fields: fKind === "form" ? fields : [],
        checklist_items: fKind === "checklist" ? items : [],
        target_percent: fKind === "checklist" ? parseFloat(fTarget) || 100 : null,
      };
      await api.post("/forms/templates", payload);
      setFormModal(false);
      setFKind("form");
      setFTitle("");
      setFDesc("");
      setFTarget("100");
      setFields([{ key: "name", label: "Full Name", type: "text", required: true }]);
      setItems([
        { id: "HL29", label: "HL 29", sub_keys: ["EXT", "INT"] },
        { id: "HL30", label: "HL 30", sub_keys: ["EXT", "INT"] },
      ]);
      setBulkInput("");
      await load();
      Alert.alert("Published", "Staff can now fill it out");
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Failed");
    }
  };

  const bulkAddItems = () => {
    const subs = subKeysInput.split(",").map((s) => s.trim()).filter(Boolean);
    if (subs.length === 0) {
      Alert.alert("Sub-tasks needed", "e.g. EXT,INT");
      return;
    }
    const lines = bulkInput.split(/[\n,]/).map((s) => s.trim()).filter(Boolean);
    if (lines.length === 0) {
      Alert.alert("Add items", "Enter one item per line (e.g. HL 29)");
      return;
    }
    const next = lines.map((label) => ({
      id: label.replace(/\s+/g, "").toUpperCase(),
      label,
      sub_keys: subs,
    }));
    setItems([...items, ...next]);
    setBulkInput("");
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
              <Text style={styles.addCtaText}>Create Form / Checklist</Text>
            </TouchableOpacity>
            <Text style={[typography.small, { marginTop: 8, marginBottom: 4 }]}>
              Build custom forms or daily checklists (e.g. truck wash). Tap a checklist to view stats.
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
                    onPress={() => openStats(t, "month")}
                  >
                    <Feather name="bar-chart-2" size={14} color="#fff" />
                    <Text style={{ color: "#fff", fontSize: 11, fontWeight: "700", marginLeft: 4 }}>Stats</Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity
                  onPress={async () => {
                    await api.delete(`/forms/templates/${t.id}`);
                    await load();
                  }}
                  style={{ marginLeft: 8 }}
                >
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
            <Text style={[typography.h3, { marginLeft: 12 }]}>New Template</Text>
          </View>
          <ScrollView contentContainerStyle={{ padding: spacing.lg }}>
            <View style={{ flexDirection: "row", gap: 8, marginBottom: 12 }}>
              {(["form", "checklist"] as const).map((k) => (
                <TouchableOpacity
                  key={k}
                  testID={`kind-${k}`}
                  style={[styles.typeChip, fKind === k && { backgroundColor: colors.primary }]}
                  onPress={() => setFKind(k)}
                >
                  <Text style={{ color: fKind === k ? "#fff" : colors.primary, fontWeight: "700" }}>
                    {k === "form" ? "Form" : "Checklist"}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <TextInput style={styles.input} placeholder="Title (e.g. Daily Truck Wash)" value={fTitle} onChangeText={setFTitle} placeholderTextColor={colors.textMuted} />
            <TextInput style={[styles.input, { height: 70 }]} placeholder="Description" value={fDesc} onChangeText={setFDesc} multiline placeholderTextColor={colors.textMuted} />

            {fKind === "form" ? (
              <>
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
              </>
            ) : (
              <>
                <Text style={[typography.label, { marginTop: 16 }]}>Sub-tasks per item (comma separated)</Text>
                <TextInput
                  testID="checklist-subkeys"
                  style={styles.input}
                  placeholder="EXT,INT"
                  value={subKeysInput}
                  onChangeText={setSubKeysInput}
                  placeholderTextColor={colors.textMuted}
                />
                <Text style={[typography.label, { marginTop: 16 }]}>Target % (e.g. 100)</Text>
                <TextInput
                  testID="checklist-target"
                  style={styles.input}
                  placeholder="100"
                  value={fTarget}
                  onChangeText={setFTarget}
                  keyboardType="numeric"
                  placeholderTextColor={colors.textMuted}
                />

                <Text style={[typography.label, { marginTop: 16 }]}>Items ({items.length})</Text>
                {items.map((it, idx) => (
                  <View key={idx} style={[styles.fieldEditor, { flexDirection: "row", alignItems: "center", gap: 8 }]}>
                    <TextInput
                      style={[styles.input, { flex: 1, marginTop: 0 }]}
                      placeholder="Label (e.g. HL 29)"
                      value={it.label}
                      onChangeText={(v) => {
                        const c = [...items];
                        c[idx] = { ...c[idx], label: v, id: v.replace(/\s+/g, "").toUpperCase() || `IT${idx}` };
                        setItems(c);
                      }}
                    />
                    <TouchableOpacity onPress={() => setItems(items.filter((_, i) => i !== idx))}>
                      <Feather name="trash-2" size={16} color={colors.alert} />
                    </TouchableOpacity>
                  </View>
                ))}
                <TouchableOpacity
                  style={[styles.modalBtn, { backgroundColor: colors.surface, marginTop: 8 }]}
                  onPress={() => {
                    const subs = subKeysInput.split(",").map((s) => s.trim()).filter(Boolean);
                    setItems([...items, { id: `IT${items.length}`, label: `Item ${items.length + 1}`, sub_keys: subs.length ? subs : ["EXT", "INT"] }]);
                  }}
                >
                  <Text style={{ color: colors.primary, fontWeight: "700" }}>+ Add Single Item</Text>
                </TouchableOpacity>

                <Text style={[typography.label, { marginTop: 16 }]}>Bulk add (one item per line)</Text>
                <TextInput
                  testID="checklist-bulk"
                  style={[styles.input, { height: 100, textAlignVertical: "top", paddingTop: 10 }]}
                  multiline
                  placeholder={"HL 29\nHL 30\nHL 31"}
                  value={bulkInput}
                  onChangeText={setBulkInput}
                  placeholderTextColor={colors.textMuted}
                />
                <TouchableOpacity
                  testID="checklist-bulk-add"
                  style={[styles.modalBtn, { backgroundColor: colors.surface, marginTop: 8 }]}
                  onPress={bulkAddItems}
                >
                  <Text style={{ color: colors.primary, fontWeight: "700" }}>Append items</Text>
                </TouchableOpacity>
              </>
            )}

            <TouchableOpacity
              testID="publish-template"
              style={[styles.modalBtn, { backgroundColor: colors.primary, marginTop: 16 }]}
              onPress={createForm}
            >
              <Text style={{ color: "#fff", fontWeight: "700" }}>Publish</Text>
            </TouchableOpacity>
          </ScrollView>
        </SafeAreaView>
      </Modal>

      {/* Stats Modal */}
      <Modal visible={!!statsTpl} animationType="slide" onRequestClose={() => setStatsTpl(null)}>
        <SafeAreaView style={{ flex: 1, backgroundColor: "#fff" }}>
          <View style={styles.header}>
            <TouchableOpacity onPress={() => setStatsTpl(null)}>
              <Feather name="x" size={24} color={colors.primary} />
            </TouchableOpacity>
            <Text style={[typography.h3, { marginLeft: 12, flex: 1 }]} numberOfLines={1}>
              {statsTpl?.title} · Stats
            </Text>
          </View>
          <View style={{ flexDirection: "row", padding: spacing.md, gap: 6 }}>
            {(["day", "week", "month", "all"] as const).map((r) => (
              <TouchableOpacity
                key={r}
                onPress={() => statsTpl && openStats(statsTpl, r)}
                style={[styles.tab, statsRange === r && styles.tabActive]}
                testID={`range-${r}`}
              >
                <Text style={[styles.tabText, statsRange === r && styles.tabTextActive]}>{r}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm }}>
            {statsBusy ? (
              <Text style={typography.body}>Loading stats…</Text>
            ) : stats ? (
              <>
                <View style={[styles.card, { flexDirection: "column", alignItems: "stretch" }]}>
                  <Text style={typography.label}>Overall completion</Text>
                  <Text style={{ fontSize: 38, fontWeight: "700", color: colors.primary, marginTop: 4 }}>
                    {stats.overall_percent}%
                  </Text>
                  <View style={{ height: 8, backgroundColor: colors.surface, borderRadius: 4, marginTop: 8, overflow: "hidden" }}>
                    <View
                      style={{
                        width: `${Math.min(100, stats.overall_percent)}%`,
                        height: "100%",
                        backgroundColor: stats.on_target ? colors.success : colors.alert,
                      }}
                    />
                  </View>
                  <Text style={[typography.small, { marginTop: 6 }]}>
                    {stats.overall_done}/{stats.overall_possible} sub-tasks completed across {stats.submissions} submissions · target {stats.target_percent || 100}%
                  </Text>
                  <Text style={{ marginTop: 6, fontWeight: "700", color: stats.on_target ? colors.success : colors.alert }}>
                    {stats.on_target ? "✓ On target" : "✗ Below target"}
                  </Text>
                </View>

                <Text style={[typography.label, { marginTop: 16 }]}>Per item</Text>
                {stats.items.map((it: any) => {
                  const total = it.sub_keys.length * stats.submissions;
                  const done = Object.values(it.counts).reduce((a: any, b: any) => a + b, 0) as number;
                  const pct = total > 0 ? Math.round((done / total) * 1000) / 10 : 0;
                  return (
                    <View key={it.id} style={[styles.card, { flexDirection: "column", alignItems: "stretch" }]}>
                      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                        <Text style={{ fontWeight: "700", color: colors.primary }}>{it.label}</Text>
                        <Text style={{ fontWeight: "700", color: pct >= (stats.target_percent || 100) ? colors.success : colors.alert }}>
                          {pct}%
                        </Text>
                      </View>
                      <View style={{ flexDirection: "row", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
                        {it.sub_keys.map((sk: string) => (
                          <View key={sk} style={[styles.typeChip, { backgroundColor: colors.surface }]}>
                            <Text style={{ fontSize: 11, fontWeight: "700", color: colors.primary }}>
                              {sk}: {it.counts[sk]}/{stats.submissions} · missed {Math.max(0, stats.submissions - it.counts[sk])}
                            </Text>
                          </View>
                        ))}
                      </View>
                    </View>
                  );
                })}
              </>
            ) : (
              <Text style={typography.body}>No data.</Text>
            )}
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
