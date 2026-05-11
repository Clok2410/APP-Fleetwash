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
import PdfFormFillModal from "../../src/components/PdfFormFillModal";

type Field = { key: string; label: string; type: string; required?: boolean; options?: string[] };

export default function FormsScreen() {
  const { user } = useAuth();
  const [tab, setTab] = useState<"templates" | "submissions">("templates");
  const [templates, setTemplates] = useState<any[]>([]);
  const [pdfTemplates, setPdfTemplates] = useState<any[]>([]);
  const [pdfSessions, setPdfSessions] = useState<any[]>([]);
  const [activePdfId, setActivePdfId] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
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
      const [t, s, p, ps, sess] = await Promise.all([
        api.get("/forms/templates"),
        api.get("/forms/submissions"),
        api.get("/pdf-forms/templates").catch(() => ({ data: [] })),
        api.get("/pdf-forms/submissions").catch(() => ({ data: [] })),
        api.get("/pdf-forms/sessions").catch(() => ({ data: [] })),
      ]);
      setTemplates(t.data);
      setSubmissions([
        ...s.data.map((x: any) => ({ ...x, _kind: "form" })),
        ...(ps.data || []).map((x: any) => ({ ...x, _kind: "pdf" })),
      ].sort((a, b) => (a.created_at < b.created_at ? 1 : -1)));
      setPdfTemplates(p.data || []);
      setPdfSessions(sess.data || []);
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
    if (tpl.kind === "checklist") {
      (tpl.checklist_items || []).forEach((it: any) => {
        (it.sub_keys || []).forEach((sk: string) => {
          init[`${it.id}_${sk}`] = false;
        });
      });
      init["_date"] = new Date().toISOString().slice(0, 10);
      init["_notes"] = "";
    } else {
      (tpl.fields || []).forEach((f: Field) => {
        init[f.key] = f.type === "checkbox" ? false : "";
      });
    }
    setValues(init);
  };

  const submit = async () => {
    if (!active) return;
    if (active.kind !== "checklist") {
      for (const f of active.fields as Field[]) {
        if (f.required && (values[f.key] === "" || values[f.key] == null)) {
          Alert.alert("Required", `Please complete: ${f.label}`);
          return;
        }
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

  const sharePdfSubmission = async (sid: string, title: string) => {
    try {
      const { data } = await api.get(`/pdf-forms/submissions/${sid}`);
      const base64 = data?.filled_pdf_base64;
      if (!base64) {
        Alert.alert("Missing PDF", "Submission has no PDF data.");
        return;
      }
      // Lazy import to keep web bundle lean
      const FileSystem = await import("expo-file-system");
      const Sharing = await import("expo-sharing");
      const { Platform } = await import("react-native");
      if (Platform.OS === "web") {
        const byteChars = atob(base64);
        const bytes = new Uint8Array(byteChars.length);
        for (let i = 0; i < byteChars.length; i++) bytes[i] = byteChars.charCodeAt(i);
        const blob = new Blob([bytes], { type: "application/pdf" });
        const url = URL.createObjectURL(blob);
        if (typeof window !== "undefined") window.open(url, "_blank");
        return;
      }
      const safe = (title || "filled").replace(/[^a-z0-9_-]+/gi, "_");
      const path = `${FileSystem.documentDirectory}${safe}_${Date.now()}.pdf`;
      await FileSystem.writeAsStringAsync(path, base64, {
        encoding: FileSystem.EncodingType.Base64,
      });
      const ok = await Sharing.isAvailableAsync();
      if (!ok) {
        Alert.alert("Saved", `PDF saved to: ${path}`);
        return;
      }
      await Sharing.shareAsync(path, { mimeType: "application/pdf", dialogTitle: title });
    } catch (e: any) {
      Alert.alert("Share failed", e.response?.data?.detail || String(e?.message || e));
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
          (templates.length === 0 && pdfTemplates.length === 0 ? (
            <View style={styles.empty}>
              <Feather name="file-plus" size={28} color={colors.textMuted} />
              <Text style={[typography.body, { textAlign: "center", marginTop: 10 }]}>
                No forms yet. {user?.role === "admin" ? "Create one from the Admin panel." : "Your admin will publish them here."}
              </Text>
            </View>
          ) : (
            <>
              {templates.map((t) => (
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
                    <Text style={[typography.small, { marginTop: 4 }]}>
                      {t.kind === "checklist"
                        ? `${(t.checklist_items || []).length} items · target ${t.target_percent || 100}%`
                        : `${t.fields?.length || 0} fields`}
                    </Text>
                  </View>
                  <Feather name="chevron-right" size={18} color={colors.textMuted} />
                </TouchableOpacity>
              ))}
              {pdfTemplates.length > 0 ? (
                <Text style={[typography.label, { marginTop: 12 }]}>PDF Fillable Forms</Text>
              ) : null}
              {pdfTemplates.map((t) => (
                <TouchableOpacity
                  key={t.id}
                  style={styles.card}
                  testID={`pdf-template-${t.id}`}
                  onPress={() => setActivePdfId(t.id)}
                  activeOpacity={0.85}
                >
                  <View style={[styles.iconWrap, { backgroundColor: "#FEE2E2" }]}>
                    <Feather name="file-text" size={18} color="#B91C1C" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.cardTitle}>{t.title}</Text>
                    {t.description ? <Text style={typography.small}>{t.description}</Text> : null}
                    <Text style={[typography.small, { marginTop: 4 }]}>
                      {t.has_acroform
                        ? `${t.field_count} fields · submit emails admin`
                        : "No fillable fields detected"}
                    </Text>
                  </View>
                  <Feather name="chevron-right" size={18} color={colors.textMuted} />
                </TouchableOpacity>
              ))}
            </>
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
                  <Feather
                    name={s._kind === "pdf" ? "file-text" : "check-circle"}
                    size={18}
                    color={s._kind === "pdf" ? "#B91C1C" : colors.success}
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.cardTitle}>{s.template_title}</Text>
                  <Text style={typography.small}>{new Date(s.created_at).toLocaleString()}</Text>
                  {s._kind === "pdf" ? (
                    <Text style={[typography.small, { marginTop: 2, color: colors.textMuted }]}>PDF · filled</Text>
                  ) : null}
                </View>
                {s._kind === "pdf" ? (
                  <TouchableOpacity
                    onPress={() => sharePdfSubmission(s.id, s.template_title)}
                    style={[styles.aiBtn, { backgroundColor: colors.primary }]}
                    testID={`share-${s.id}`}
                  >
                    <Feather name="share-2" size={14} color="#fff" />
                    <Text style={{ color: "#fff", fontSize: 11, fontWeight: "700", marginLeft: 4 }}>PDF</Text>
                  </TouchableOpacity>
                ) : (
                  <TouchableOpacity onPress={() => summarize(s)} style={styles.aiBtn} testID={`ai-${s.id}`}>
                    <Feather name="zap" size={14} color="#fff" />
                    <Text style={{ color: "#fff", fontSize: 11, fontWeight: "700", marginLeft: 4 }}>AI</Text>
                  </TouchableOpacity>
                )}
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

            {active?.kind === "checklist" ? (
              <>
                <Text style={typography.label}>Date</Text>
                <TextInput
                  testID="checklist-date"
                  style={styles.fieldInput}
                  value={String(values["_date"] ?? "")}
                  onChangeText={(v) => setValues({ ...values, _date: v })}
                  placeholder="YYYY-MM-DD"
                  placeholderTextColor={colors.textMuted}
                />
                <View style={{ marginTop: 16, borderRadius: radius.md, overflow: "hidden", borderWidth: 1, borderColor: colors.border }}>
                  <View style={{ flexDirection: "row", backgroundColor: colors.surface, padding: 10 }}>
                    <Text style={{ flex: 1, fontWeight: "700", fontSize: 12, color: colors.textSecondary }}>ITEM</Text>
                    {(active.checklist_items?.[0]?.sub_keys || []).map((sk: string) => (
                      <Text key={sk} style={{ width: 64, textAlign: "center", fontWeight: "700", fontSize: 12, color: colors.textSecondary }}>
                        {sk}
                      </Text>
                    ))}
                  </View>
                  {(active.checklist_items || []).map((it: any, i: number) => (
                    <View
                      key={it.id}
                      style={{
                        flexDirection: "row",
                        alignItems: "center",
                        padding: 10,
                        backgroundColor: i % 2 === 0 ? "#fff" : colors.surface,
                      }}
                    >
                      <Text style={{ flex: 1, fontWeight: "600", color: colors.primary }}>{it.label}</Text>
                      {it.sub_keys.map((sk: string) => {
                        const k = `${it.id}_${sk}`;
                        const v = !!values[k];
                        return (
                          <TouchableOpacity
                            key={sk}
                            testID={`cb-${k}`}
                            onPress={() => setValues({ ...values, [k]: !v })}
                            style={{
                              width: 64,
                              alignItems: "center",
                              justifyContent: "center",
                            }}
                            activeOpacity={0.7}
                          >
                            <View
                              style={{
                                width: 28,
                                height: 28,
                                borderRadius: 6,
                                borderWidth: 2,
                                borderColor: v ? colors.success : colors.border,
                                backgroundColor: v ? colors.success : "#fff",
                                alignItems: "center",
                                justifyContent: "center",
                              }}
                            >
                              {v && <Feather name="check" size={18} color="#fff" />}
                            </View>
                          </TouchableOpacity>
                        );
                      })}
                    </View>
                  ))}
                </View>
                <Text style={[typography.label, { marginTop: 16 }]}>Notes</Text>
                <TextInput
                  testID="checklist-notes"
                  style={[styles.fieldInput, { height: 100, textAlignVertical: "top" }]}
                  multiline
                  value={String(values["_notes"] ?? "")}
                  onChangeText={(v) => setValues({ ...values, _notes: v })}
                  placeholder="Any exceptions, missed items, or comments…"
                  placeholderTextColor={colors.textMuted}
                />
              </>
            ) : (
              (active?.fields || []).map((f: Field) => (
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
              ))
            )}
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
      {/* PDF Fill modal */}
      <PdfFormFillModal
        templateId={activePdfId}
        sessionId={activeSessionId}
        isAdmin={user?.role === "admin"}
        onClose={async () => {
          setActivePdfId(null);
          setActiveSessionId(null);
          await load();
        }}
      />
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
