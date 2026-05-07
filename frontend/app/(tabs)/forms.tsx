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
  Switch,
  ActivityIndicator,
  RefreshControl,
} from "react-native";
import { useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { SafeAreaView } from "react-native-safe-area-context";
import { api } from "../../src/api";
import { useAuth } from "../../src/auth";
import { colors, spacing, radius, typography } from "../../src/theme";

type Field = { key: string; label: string; type: string; required?: boolean; options?: string[] };

export default function FormsScreen() {
  const { user } = useAuth();
  const [tab, setTab] = useState<"templates" | "submissions">("templates");
  const [templates, setTemplates] = useState<any[]>([]);
  const [submissions, setSubmissions] = useState<any[]>([]);
  const [active, setActive] = useState<any>(null); // template being filled
  const [values, setValues] = useState<Record<string, any>>({});
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [summaryFor, setSummaryFor] = useState<any>(null);
  const [summary, setSummary] = useState<string>("");
  const [summaryBusy, setSummaryBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [t, s] = await Promise.all([api.get("/forms/templates"), api.get("/forms/submissions")]);
      setTemplates(t.data);
      setSubmissions(s.data);
    } catch {}
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const startFill = (tpl: any) => {
    setActive(tpl);
    const init: Record<string, any> = {};
    (tpl.fields || []).forEach((f: Field) => {
      init[f.key] = f.type === "checkbox" ? false : "";
    });
    setValues(init);
  };

  const submit = async () => {
    if (!active) return;
    for (const f of active.fields as Field[]) {
      if (f.required && (values[f.key] === "" || values[f.key] == null)) {
        Alert.alert("Required", `Please complete: ${f.label}`);
        return;
      }
    }
    setSubmitting(true);
    try {
      await api.post("/forms/submissions", { template_id: active.id, values });
      setActive(null);
      setValues({});
      await load();
      setTab("submissions");
      Alert.alert("Submitted", "Form sent successfully");
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Failed");
    } finally {
      setSubmitting(false);
    }
  };

  const summarize = async (sub: any) => {
    setSummaryFor(sub);
    setSummary(sub.ai_summary || "");
    if (sub.ai_summary) return;
    setSummaryBusy(true);
    try {
      const { data } = await api.post(`/forms/submissions/${sub.id}/summarize`);
      setSummary(data.summary);
      await load();
    } catch (e: any) {
      Alert.alert("AI failed", e.response?.data?.detail || "Try again");
    } finally {
      setSummaryBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <View style={styles.header}>
        <Text style={typography.label}>Compliance</Text>
        <Text style={typography.h2}>Fillable Forms.</Text>
      </View>

      <View style={styles.tabs}>
        <TouchableOpacity
          testID="tab-templates"
          onPress={() => setTab("templates")}
          style={[styles.tab, tab === "templates" && styles.tabActive]}
        >
          <Text style={[styles.tabText, tab === "templates" && styles.tabTextActive]}>Available</Text>
        </TouchableOpacity>
        <TouchableOpacity
          testID="tab-submissions"
          onPress={() => setTab("submissions")}
          style={[styles.tab, tab === "submissions" && styles.tabActive]}
        >
          <Text style={[styles.tabText, tab === "submissions" && styles.tabTextActive]}>
            My Submissions · {submissions.length}
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
        {tab === "templates" &&
          (templates.length === 0 ? (
            <View style={styles.empty}>
              <Feather name="file-plus" size={28} color={colors.textMuted} />
              <Text style={[typography.body, { textAlign: "center", marginTop: 10 }]}>
                No forms yet. {user?.role === "admin" ? "Create one from the Admin panel." : "Your admin will publish them here."}
              </Text>
            </View>
          ) : (
            templates.map((t) => (
              <TouchableOpacity
                key={t.id}
                style={styles.card}
                onPress={() => startFill(t)}
                testID={`template-${t.id}`}
              >
                <View style={[styles.iconWrap, { backgroundColor: colors.brandSoft }]}>
                  <Feather name="edit-3" size={18} color={colors.brand} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.cardTitle}>{t.title}</Text>
                  {t.description ? <Text style={typography.small}>{t.description}</Text> : null}
                  <Text style={[typography.small, { marginTop: 4 }]}>{t.fields?.length || 0} fields</Text>
                </View>
                <Feather name="chevron-right" size={18} color={colors.textMuted} />
              </TouchableOpacity>
            ))
          ))}

        {tab === "submissions" &&
          (submissions.length === 0 ? (
            <View style={styles.empty}>
              <Feather name="inbox" size={28} color={colors.textMuted} />
              <Text style={[typography.body, { textAlign: "center", marginTop: 10 }]}>
                No submissions yet.
              </Text>
            </View>
          ) : (
            submissions.map((s) => (
              <View key={s.id} style={styles.card}>
                <View style={[styles.iconWrap, { backgroundColor: colors.surface }]}>
                  <Feather name="check-circle" size={18} color={colors.success} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.cardTitle}>{s.template_title}</Text>
                  <Text style={typography.small}>{new Date(s.created_at).toLocaleString()}</Text>
                </View>
                <TouchableOpacity onPress={() => summarize(s)} style={styles.aiBtn} testID={`ai-${s.id}`}>
                  <Feather name="zap" size={14} color="#fff" />
                  <Text style={{ color: "#fff", fontSize: 11, fontWeight: "700", marginLeft: 4 }}>AI</Text>
                </TouchableOpacity>
              </View>
            ))
          ))}
      </ScrollView>

      {/* Fill form modal */}
      <Modal visible={!!active} animationType="slide" onRequestClose={() => setActive(null)}>
        <SafeAreaView style={{ flex: 1, backgroundColor: "#fff" }}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => setActive(null)}>
              <Feather name="x" size={24} color={colors.primary} />
            </TouchableOpacity>
            <Text style={[typography.h3, { flex: 1, marginLeft: 12 }]}>{active?.title}</Text>
          </View>
          <ScrollView contentContainerStyle={{ padding: spacing.lg }}>
            {active?.description ? (
              <Text style={[typography.body, { marginBottom: spacing.md }]}>{active.description}</Text>
            ) : null}
            {(active?.fields || []).map((f: Field) => (
              <View key={f.key} style={{ marginBottom: spacing.md }}>
                <Text style={typography.label}>
                  {f.label} {f.required && <Text style={{ color: colors.alert }}>*</Text>}
                </Text>
                {f.type === "checkbox" ? (
                  <View style={{ flexDirection: "row", alignItems: "center", marginTop: 8 }}>
                    <Switch
                      value={!!values[f.key]}
                      onValueChange={(v) => setValues({ ...values, [f.key]: v })}
                    />
                    <Text style={{ marginLeft: 8 }}>{values[f.key] ? "Yes" : "No"}</Text>
                  </View>
                ) : f.type === "select" ? (
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                    {(f.options || []).map((opt) => (
                      <TouchableOpacity
                        key={opt}
                        onPress={() => setValues({ ...values, [f.key]: opt })}
                        style={[
                          styles.chip,
                          values[f.key] === opt && { backgroundColor: colors.primary },
                        ]}
                      >
                        <Text
                          style={{
                            color: values[f.key] === opt ? "#fff" : colors.primary,
                            fontWeight: "600",
                            fontSize: 13,
                          }}
                        >
                          {opt}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                ) : (
                  <TextInput
                    testID={`field-${f.key}`}
                    style={[styles.fieldInput, f.type === "textarea" && { height: 100, textAlignVertical: "top" }]}
                    multiline={f.type === "textarea" || f.type === "signature"}
                    keyboardType={f.type === "number" ? "numeric" : "default"}
                    value={String(values[f.key] ?? "")}
                    onChangeText={(v) => setValues({ ...values, [f.key]: v })}
                    placeholder={f.type === "signature" ? "Type your full name to sign" : ""}
                    placeholderTextColor={colors.textMuted}
                  />
                )}
              </View>
            ))}
            <TouchableOpacity
              testID="submit-form"
              style={styles.submitBtn}
              onPress={submit}
              disabled={submitting}
              activeOpacity={0.85}
            >
              {submitting ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={{ color: "#fff", fontWeight: "700", fontSize: 16 }}>
                  Submit Form
                </Text>
              )}
            </TouchableOpacity>
          </ScrollView>
        </SafeAreaView>
      </Modal>

      {/* AI summary modal */}
      <Modal visible={!!summaryFor} animationType="fade" transparent onRequestClose={() => setSummaryFor(null)}>
        <View style={styles.modalBg}>
          <View style={[styles.modalCard, { borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl }]}>
            <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 8 }}>
              <View style={[styles.iconWrap, { backgroundColor: colors.brandSoft }]}>
                <Feather name="zap" size={16} color={colors.brand} />
              </View>
              <Text style={[typography.h3, { marginLeft: 8 }]}>AI Summary</Text>
            </View>
            <Text style={[typography.small, { marginBottom: 12 }]}>{summaryFor?.template_title}</Text>
            {summaryBusy ? (
              <ActivityIndicator color={colors.brand} />
            ) : (
              <Text style={typography.body}>{summary || "No summary available."}</Text>
            )}
            <TouchableOpacity
              style={[styles.btnPrimary, { marginTop: 14, height: 44, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" }]}
              onPress={() => setSummaryFor(null)}
            >
              <Text style={{ color: "#fff", fontWeight: "700" }}>Close</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
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
  card: {
    backgroundColor: "#fff",
    borderRadius: radius.lg,
    padding: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderWidth: 1,
    borderColor: colors.border,
  },
  iconWrap: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
  },
  cardTitle: { fontSize: 15, fontWeight: "600", color: colors.primary },
  aiBtn: {
    backgroundColor: colors.brand,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: radius.pill,
    flexDirection: "row",
    alignItems: "center",
  },
  empty: { padding: spacing.xl, alignItems: "center" },
  modalHeader: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.md,
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
  },
  fieldInput: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: 12,
    fontSize: 15,
    marginTop: 6,
    minHeight: 48,
  },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
  },
  submitBtn: {
    height: 56,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    marginTop: spacing.md,
  },
  modalBg: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.4)" },
  modalCard: { backgroundColor: "#fff", padding: spacing.lg },
  btnPrimary: { backgroundColor: colors.primary },
});
