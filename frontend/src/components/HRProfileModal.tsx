// Admin HR profile drawer — opens for a single staff member.
// Shows personal details, holiday/sick summary, and HR issuances with full audit trail.
// Includes "Issue document" CTA that posts to /hr/issue.
import React, { useEffect, useState, useCallback } from "react";
import { Modal, View, Text, TouchableOpacity, ScrollView, TextInput, Alert, StyleSheet, Platform } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { api } from "../api";
import { colors, radius, spacing, typography } from "../theme";

type Props = {
  visible: boolean;
  userId: string | null;
  onClose: () => void;
  onReload?: () => void;
};

export default function HRProfileModal({ visible, userId, onClose, onReload }: Props) {
  const [profile, setProfile] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [pdfTemplates, setPdfTemplates] = useState<any[]>([]);
  // Issue form state
  const [issueOpen, setIssueOpen] = useState(false);
  const [issueTemplate, setIssueTemplate] = useState<string>("");
  const [issueExpires, setIssueExpires] = useState<string>("");
  const [issueMessage, setIssueMessage] = useState<string>("");
  // Audit drawer state
  const [auditFor, setAuditFor] = useState<any>(null);

  const load = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/hr/staff/${userId}/profile`);
      setProfile(data);
    } catch (e: any) {
      Alert.alert("Failed", e.response?.data?.detail || "Could not load profile");
    } finally {
      setLoading(false);
    }
  }, [userId]);

  const loadTemplates = useCallback(async () => {
    try {
      const { data } = await api.get("/pdf-forms/templates");
      setPdfTemplates(Array.isArray(data) ? data : []);
    } catch (e) {
      setPdfTemplates([]);
    }
  }, []);

  useEffect(() => {
    if (visible && userId) {
      load();
      loadTemplates();
    } else {
      setProfile(null);
      setIssueOpen(false);
      setIssueTemplate("");
      setIssueExpires("");
      setIssueMessage("");
      setAuditFor(null);
    }
  }, [visible, userId, load, loadTemplates]);

  const submitIssue = async () => {
    if (!issueTemplate) return Alert.alert("Pick a template");
    if (issueExpires && !/^\d{4}-\d{2}-\d{2}$/.test(issueExpires)) {
      return Alert.alert("Expiry date", "Use YYYY-MM-DD or leave empty.");
    }
    try {
      await api.post("/hr/issue", {
        template_id: issueTemplate,
        user_id: userId,
        expires_at: issueExpires || null,
        message: issueMessage || "",
      });
      setIssueOpen(false);
      setIssueTemplate("");
      setIssueExpires("");
      setIssueMessage("");
      await load();
      onReload && onReload();
    } catch (e: any) {
      Alert.alert("Failed", e.response?.data?.detail || "Could not issue document");
    }
  };

  const cancelIssuance = (iid: string) => {
    Alert.alert("Cancel issuance?", "Staff will no longer be able to sign this document.", [
      { text: "Keep", style: "cancel" },
      {
        text: "Cancel",
        style: "destructive",
        onPress: async () => {
          try {
            await api.post(`/hr/issuances/${iid}/cancel`);
            await load();
          } catch (e: any) {
            Alert.alert("Failed", e.response?.data?.detail || "Could not cancel");
          }
        },
      },
    ]);
  };

  const downloadPdf = async (i: any) => {
    try {
      const filename = `${(i.template_title || "doc").replace(/[^a-z0-9_-]+/gi, "_")}_${(i.user_name || "user").replace(/[^a-z0-9]+/gi, "_")}_signed.pdf`;
      if (Platform.OS === "web") {
        const AsyncStorage = (await import("@react-native-async-storage/async-storage")).default;
        const token = await AsyncStorage.getItem("access_token");
        const resp = await fetch(`/api/hr/issuances/${i.id}/pdf`, { headers: { Authorization: `Bearer ${token}` } });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } else {
        const FileSystem = await import("expo-file-system");
        const Sharing = await import("expo-sharing");
        const AsyncStorage = (await import("@react-native-async-storage/async-storage")).default;
        const token = await AsyncStorage.getItem("access_token");
        const baseURL = (api.defaults?.baseURL || "").replace(/\/$/, "");
        const target = `${FileSystem.cacheDirectory}${filename}`;
        const result = await FileSystem.downloadAsync(
          `${baseURL}/hr/issuances/${i.id}/pdf`,
          target,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        if (result.status === 200 && (await Sharing.isAvailableAsync())) {
          await Sharing.shareAsync(result.uri);
        }
      }
    } catch (e: any) {
      Alert.alert("Download failed", String(e?.message || e));
    }
  };

  const statusColor = (s: string) => {
    if (s === "signed") return "#0F766E";
    if (s === "expired" || s === "cancelled") return colors.alert;
    if (s === "read") return "#F59E0B";
    return colors.brand;
  };

  if (!profile) {
    return (
      <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
        <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }}>
          <View style={styles.header}>
            <TouchableOpacity onPress={onClose} style={styles.closeBtn} testID="hr-close">
              <Feather name="x" size={20} color={colors.primary} />
            </TouchableOpacity>
            <Text style={typography.h2}>HR Profile</Text>
          </View>
          <Text style={[typography.small, { textAlign: "center", marginTop: 32 }]}>
            {loading ? "Loading…" : "—"}
          </Text>
        </SafeAreaView>
      </Modal>
    );
  }

  const u = profile.user || {};
  const h = profile.holiday || {};

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }}>
        <View style={styles.header}>
          <TouchableOpacity onPress={onClose} style={styles.closeBtn} testID="hr-close">
            <Feather name="x" size={20} color={colors.primary} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={typography.h2}>{u.name || "(no name)"}</Text>
            <Text style={typography.small}>{u.email}</Text>
          </View>
        </View>

        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}>
          {/* Personal details */}
          <View style={styles.card}>
            <Text style={typography.label}>Personal details</Text>
            <Row k="Phone" v={u.phone} />
            <Row k="Date of birth" v={u.dob} />
            <Row k="PPS number" v={u.pps_number} />
            <Row k="Employment type" v={u.employment_type} />
            <Row k="Start date" v={u.start_date} />
            <Row k="Holiday entitlement" v={`${u.holiday_entitlement ?? 20} days/yr`} />
          </View>

          {/* Holiday summary */}
          <View style={styles.card}>
            <Text style={typography.label}>Holiday balance (this year)</Text>
            <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 4 }}>
              <Stat label="Used" value={h.used_days ?? 0} />
              <Stat label="Pending" value={h.pending_days ?? 0} />
              <Stat label="Remaining" value={h.remaining ?? 0} accent={colors.brand} />
            </View>
          </View>

          {/* HR documents */}
          <View style={styles.card}>
            <View style={{ flexDirection: "row", alignItems: "center" }}>
              <Text style={[typography.label, { flex: 1 }]}>
                HR documents ({(profile.issuances || []).length})
              </Text>
              <TouchableOpacity
                testID="hr-open-issue"
                onPress={() => setIssueOpen(true)}
                style={styles.issueBtn}
              >
                <Feather name="plus" size={13} color="#fff" />
                <Text style={{ color: "#fff", fontSize: 12, fontWeight: "700", marginLeft: 4 }}>Issue</Text>
              </TouchableOpacity>
            </View>

            {(profile.issuances || []).length === 0 ? (
              <Text style={[typography.small, { textAlign: "center", marginTop: 8 }]}>No documents issued yet.</Text>
            ) : (
              profile.issuances.map((i: any) => (
                <View key={i.id} style={styles.iRow} testID={`hr-issuance-${i.id}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontWeight: "700", color: colors.primary }}>{i.template_title}</Text>
                    <Text style={typography.small}>
                      Issued {i.issued_at ? new Date(i.issued_at).toLocaleDateString() : "—"} by {i.issued_by_name}
                    </Text>
                    {i.expires_at ? (
                      <Text style={typography.small}>
                        <Feather name="clock" size={10} color={colors.textMuted} /> Expires {i.expires_at}
                      </Text>
                    ) : null}
                    {i.signed_at ? (
                      <Text style={[typography.small, { color: "#0F766E", marginTop: 2, fontWeight: "600" }]}>
                        <Feather name="check-circle" size={10} color="#0F766E" /> Signed {new Date(i.signed_at).toLocaleString()}
                      </Text>
                    ) : null}
                  </View>
                  <View style={{ alignItems: "flex-end", gap: 6 }}>
                    <View style={[styles.statusBadge, { backgroundColor: statusColor(i.status) }]}>
                      <Text style={{ color: "#fff", fontWeight: "700", fontSize: 10 }}>
                        {(i.status || "").toUpperCase()}
                      </Text>
                    </View>
                    <View style={{ flexDirection: "row", gap: 6 }}>
                      <TouchableOpacity onPress={() => setAuditFor(i)} testID={`hr-audit-${i.id}`}>
                        <Feather name="list" size={14} color={colors.textMuted} />
                      </TouchableOpacity>
                      {i.has_signed_pdf && (
                        <TouchableOpacity onPress={() => downloadPdf(i)} testID={`hr-download-${i.id}`}>
                          <Feather name="download" size={14} color={colors.brand} />
                        </TouchableOpacity>
                      )}
                      {!["signed", "cancelled"].includes(i.status) && (
                        <TouchableOpacity onPress={() => cancelIssuance(i.id)}>
                          <Feather name="x-circle" size={14} color={colors.alert} />
                        </TouchableOpacity>
                      )}
                    </View>
                  </View>
                </View>
              ))
            )}
          </View>
        </ScrollView>

        {/* Issue document modal */}
        <Modal visible={issueOpen} animationType="slide" transparent onRequestClose={() => setIssueOpen(false)}>
          <View style={styles.subBg}>
            <View style={styles.subCard}>
              <Text style={typography.h3}>Issue HR document to {u.name}</Text>
              <Text style={[typography.small, { marginTop: 4, marginBottom: 8 }]}>
                Pick a PDF template. Staff will be required to read & sign.
              </Text>
              <ScrollView style={{ maxHeight: 180 }}>
                {pdfTemplates.length === 0 ? (
                  <Text style={typography.small}>No PDF templates available — upload one in PDF Forms first.</Text>
                ) : (
                  pdfTemplates.map((t: any) => (
                    <TouchableOpacity
                      key={t.id}
                      testID={`hr-pick-${t.id}`}
                      onPress={() => setIssueTemplate(t.id)}
                      style={[styles.tplRow, issueTemplate === t.id && styles.tplRowActive]}
                    >
                      <Feather name="file-text" size={14} color={issueTemplate === t.id ? "#fff" : colors.brand} />
                      <Text
                        style={{
                          marginLeft: 6,
                          fontWeight: "700",
                          color: issueTemplate === t.id ? "#fff" : colors.primary,
                          fontSize: 13,
                          flex: 1,
                        }}
                        numberOfLines={1}
                      >
                        {t.title}
                      </Text>
                    </TouchableOpacity>
                  ))
                )}
              </ScrollView>
              <Text style={[typography.small, { marginTop: 8 }]}>Expiry (optional, YYYY-MM-DD)</Text>
              <TextInput
                testID="hr-expires"
                value={issueExpires}
                onChangeText={setIssueExpires}
                placeholder="e.g. 2027-05-20"
                placeholderTextColor={colors.textMuted}
                style={styles.input}
              />
              <Text style={[typography.small, { marginTop: 8 }]}>Message to staff (optional)</Text>
              <TextInput
                testID="hr-message"
                value={issueMessage}
                onChangeText={setIssueMessage}
                placeholder="Please review and sign the attached document."
                placeholderTextColor={colors.textMuted}
                multiline
                style={[styles.input, { height: 64 }]}
              />
              <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
                <TouchableOpacity style={[styles.btn, styles.btnGhost]} onPress={() => setIssueOpen(false)}>
                  <Text style={styles.btnGhostText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="hr-submit-issue" style={[styles.btn, styles.btnPrimary]} onPress={submitIssue}>
                  <Text style={styles.btnPrimaryText}>Issue document</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

        {/* Audit trail modal */}
        <Modal visible={!!auditFor} animationType="slide" transparent onRequestClose={() => setAuditFor(null)}>
          <View style={styles.subBg}>
            <View style={styles.subCard}>
              <Text style={typography.h3}>Audit trail</Text>
              <Text style={typography.small}>{auditFor?.template_title}</Text>
              <ScrollView style={{ maxHeight: 360, marginTop: 8 }}>
                {(auditFor?.audit || []).map((e: any, idx: number) => (
                  <View key={idx} style={styles.auditRow}>
                    <Feather
                      name={
                        e.kind === "issued"
                          ? "send"
                          : e.kind === "read"
                          ? "eye"
                          : e.kind === "signed"
                          ? "edit-3"
                          : e.kind === "cancelled"
                          ? "x-circle"
                          : e.kind === "expired"
                          ? "clock"
                          : "circle"
                      }
                      size={14}
                      color={colors.brand}
                    />
                    <View style={{ flex: 1, marginLeft: 8 }}>
                      <Text style={{ fontWeight: "700", color: colors.primary, fontSize: 13 }}>
                        {e.kind?.toUpperCase()} · {e.actor_name || "system"}
                      </Text>
                      <Text style={typography.small}>
                        {e.at ? new Date(e.at).toLocaleString() : ""} · IP {e.ip || "–"}
                      </Text>
                      {e.user_agent ? (
                        <Text style={[typography.small, { color: colors.textMuted }]} numberOfLines={1}>
                          {e.user_agent}
                        </Text>
                      ) : null}
                    </View>
                  </View>
                ))}
              </ScrollView>
              <TouchableOpacity style={[styles.btn, styles.btnGhost, { marginTop: 12 }]} onPress={() => setAuditFor(null)}>
                <Text style={styles.btnGhostText}>Close</Text>
              </TouchableOpacity>
            </View>
          </View>
        </Modal>
      </SafeAreaView>
    </Modal>
  );
}

function Row({ k, v }: { k: string; v?: any }) {
  return (
    <View style={{ flexDirection: "row", paddingVertical: 4 }}>
      <Text style={{ width: 140, color: colors.textMuted, fontSize: 12 }}>{k}</Text>
      <Text style={{ flex: 1, color: colors.primary, fontSize: 12 }}>{v || "—"}</Text>
    </View>
  );
}

function Stat({ label, value, accent }: { label: string; value: any; accent?: string }) {
  return (
    <View style={{ flex: 1, alignItems: "center" }}>
      <Text style={{ fontSize: 22, fontWeight: "800", color: accent || colors.primary }}>{value}</Text>
      <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 2, fontWeight: "700" }}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: "#fff",
    gap: 12,
  },
  closeBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
  },
  card: {
    backgroundColor: "#fff",
    borderRadius: radius.lg,
    padding: 14,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: colors.border,
  },
  iRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: "#F1F5F9",
    marginTop: 6,
  },
  statusBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999 },
  issueBtn: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: colors.brand,
    borderRadius: 999,
  },
  subBg: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.4)" },
  subCard: {
    backgroundColor: "#fff",
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: spacing.lg,
  },
  tplRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: colors.surface,
    marginBottom: 4,
  },
  tplRowActive: { backgroundColor: colors.brand },
  input: {
    height: 40,
    borderRadius: 8,
    paddingHorizontal: 10,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    color: colors.primary,
    fontSize: 13,
    marginTop: 4,
  },
  btn: { flex: 1, alignItems: "center", justifyContent: "center", paddingVertical: 12, borderRadius: 999 },
  btnGhost: { backgroundColor: colors.surface },
  btnGhostText: { color: colors.primary, fontWeight: "700" },
  btnPrimary: { backgroundColor: colors.primary },
  btnPrimaryText: { color: "#fff", fontWeight: "700" },
  auditRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: "#F1F5F9",
  },
});
