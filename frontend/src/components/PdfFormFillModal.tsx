import React, { useEffect, useMemo, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Switch,
  ActivityIndicator,
  Alert,
  Modal,
  Platform,
} from "react-native";
import { Feather } from "@expo/vector-icons";
import { SafeAreaView } from "react-native-safe-area-context";
import * as FileSystem from "expo-file-system";
import * as Sharing from "expo-sharing";
import { api } from "../api";
import { colors, spacing, radius, typography } from "../theme";

type PdfField = {
  name: string;
  type: "text" | "checkbox" | "radio" | "select";
  value?: string;
  options?: string[] | null;
};

type Props = {
  templateId: string | null;
  onClose: () => void;
};

export default function PdfFormFillModal({ templateId, onClose }: Props) {
  const [tpl, setTpl] = useState<any>(null);
  const [values, setValues] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [filledBase64, setFilledBase64] = useState<string | null>(null);
  const [submission, setSubmission] = useState<any>(null);
  const [flatten, setFlatten] = useState(true);

  useEffect(() => {
    if (!templateId) {
      setTpl(null);
      setValues({});
      setFilledBase64(null);
      setSubmission(null);
      return;
    }
    setLoading(true);
    api
      .get(`/pdf-forms/templates/${templateId}`)
      .then(({ data }) => {
        setTpl(data);
        const init: Record<string, any> = {};
        (data.fields || []).forEach((f: PdfField) => {
          if (f.type === "checkbox") init[f.name] = false;
          else init[f.name] = f.value || "";
        });
        setValues(init);
      })
      .catch((e) => Alert.alert("Error", e.response?.data?.detail || "Could not load template"))
      .finally(() => setLoading(false));
  }, [templateId]);

  const fields: PdfField[] = useMemo(() => tpl?.fields || [], [tpl]);

  const submit = async () => {
    if (!tpl) return;
    setSubmitting(true);
    try {
      const { data } = await api.post(`/pdf-forms/templates/${tpl.id}/fill`, {
        values,
        flatten,
      });
      setSubmission(data);
      setFilledBase64(data.filled_pdf_base64);
    } catch (e: any) {
      Alert.alert("Submit failed", e.response?.data?.detail || "Try again");
    } finally {
      setSubmitting(false);
    }
  };

  const sharePdf = async () => {
    if (!filledBase64 || !tpl) return;
    try {
      if (Platform.OS === "web") {
        // Web fallback — open in a new window
        const blob = b64ToBlob(filledBase64, "application/pdf");
        const url = URL.createObjectURL(blob);
        if (typeof window !== "undefined") window.open(url, "_blank");
        return;
      }
      const safe = (tpl.title || "filled").replace(/[^a-z0-9_-]+/gi, "_");
      const path = `${FileSystem.documentDirectory}${safe}_${Date.now()}.pdf`;
      await FileSystem.writeAsStringAsync(path, filledBase64, {
        encoding: FileSystem.EncodingType.Base64,
      });
      const ok = await Sharing.isAvailableAsync();
      if (!ok) {
        Alert.alert("Saved", `PDF saved to: ${path}`);
        return;
      }
      await Sharing.shareAsync(path, {
        mimeType: "application/pdf",
        dialogTitle: tpl.title,
      });
    } catch (e: any) {
      Alert.alert("Share failed", String(e?.message || e));
    }
  };

  const close = () => {
    setTpl(null);
    setValues({});
    setFilledBase64(null);
    setSubmission(null);
    onClose();
  };

  return (
    <Modal visible={!!templateId} animationType="slide" onRequestClose={close}>
      <SafeAreaView style={{ flex: 1, backgroundColor: "#fff" }}>
        <View style={styles.header}>
          <TouchableOpacity onPress={close} testID="pdf-fill-close">
            <Feather name="x" size={24} color={colors.primary} />
          </TouchableOpacity>
          <Text style={[typography.h3, { flex: 1, marginLeft: 12 }]} numberOfLines={1}>
            {tpl?.title || "Loading…"}
          </Text>
        </View>

        {loading ? (
          <View style={styles.center}>
            <ActivityIndicator color={colors.primary} />
          </View>
        ) : tpl ? (
          <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 40 }}>
            {tpl.description ? (
              <Text style={[typography.body, { marginBottom: spacing.md }]}>{tpl.description}</Text>
            ) : null}

            {!tpl.has_acroform || fields.length === 0 ? (
              <View style={styles.warn}>
                <Feather name="alert-triangle" size={16} color="#92400E" />
                <Text style={{ color: "#78350F", marginLeft: 8, flex: 1 }}>
                  No fillable fields detected in this PDF. Ask admin to upload an AcroForm-enabled PDF.
                </Text>
              </View>
            ) : null}

            {fields.map((f) => (
              <View key={f.name} style={{ marginBottom: spacing.md }}>
                <Text style={typography.label} numberOfLines={2}>
                  {prettyName(f.name)}
                </Text>
                {f.type === "checkbox" ? (
                  <View style={{ flexDirection: "row", alignItems: "center", marginTop: 8 }}>
                    <Switch
                      value={!!values[f.name]}
                      onValueChange={(v) => setValues({ ...values, [f.name]: v })}
                    />
                    <Text style={{ marginLeft: 8 }}>{values[f.name] ? "Checked" : "Unchecked"}</Text>
                  </View>
                ) : f.type === "select" || f.type === "radio" ? (
                  <View style={styles.chipRow}>
                    {(f.options || []).map((opt) => {
                      const active = values[f.name] === opt;
                      return (
                        <TouchableOpacity
                          key={opt}
                          onPress={() => setValues({ ...values, [f.name]: opt })}
                          style={[styles.chip, active && { backgroundColor: colors.primary }]}
                        >
                          <Text style={{ color: active ? "#fff" : colors.primary, fontWeight: "600", fontSize: 13 }}>
                            {opt}
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                ) : (
                  <TextInput
                    style={styles.input}
                    value={String(values[f.name] ?? "")}
                    onChangeText={(v) => setValues({ ...values, [f.name]: v })}
                    placeholder=""
                    placeholderTextColor={colors.textMuted}
                  />
                )}
              </View>
            ))}

            {fields.length > 0 && (
              <View style={styles.flattenRow}>
                <Switch value={flatten} onValueChange={setFlatten} />
                <Text style={{ marginLeft: 8, color: colors.textSecondary }}>
                  Flatten (lock fields after fill)
                </Text>
              </View>
            )}

            {!filledBase64 ? (
              <TouchableOpacity
                testID="pdf-fill-submit"
                style={styles.submit}
                onPress={submit}
                disabled={submitting || fields.length === 0}
                activeOpacity={0.85}
              >
                {submitting ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <>
                    <Feather name="check-circle" size={16} color="#fff" />
                    <Text style={styles.submitText}>Generate Filled PDF</Text>
                  </>
                )}
              </TouchableOpacity>
            ) : (
              <View style={{ marginTop: spacing.md }}>
                <View style={styles.successCard}>
                  <Feather name="file-text" size={20} color={colors.success} />
                  <Text style={{ marginLeft: 8, color: colors.primary, fontWeight: "700", flex: 1 }}>
                    Filled PDF ready
                    {submission?.size_bytes ? ` · ${formatBytes(submission.size_bytes)}` : ""}
                  </Text>
                </View>
                <TouchableOpacity
                  testID="pdf-fill-share"
                  style={[styles.submit, { backgroundColor: colors.brand }]}
                  onPress={sharePdf}
                  activeOpacity={0.85}
                >
                  <Feather name="share-2" size={16} color="#fff" />
                  <Text style={styles.submitText}>Share / Save PDF</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.submit, { backgroundColor: colors.surface, marginTop: 8 }]}
                  onPress={() => {
                    setFilledBase64(null);
                    setSubmission(null);
                  }}
                  activeOpacity={0.85}
                >
                  <Text style={[styles.submitText, { color: colors.primary }]}>Edit Again</Text>
                </TouchableOpacity>
              </View>
            )}
          </ScrollView>
        ) : null}
      </SafeAreaView>
    </Modal>
  );
}

function prettyName(name: string) {
  return name
    .replace(/[_\.]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\s+/g, " ")
    .trim();
}

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function b64ToBlob(b64: string, mime = "application/octet-stream") {
  const byteChars = atob(b64);
  const byteNumbers = new Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i++) byteNumbers[i] = byteChars.charCodeAt(i);
  return new Blob([new Uint8Array(byteNumbers)], { type: mime });
}

const styles = StyleSheet.create({
  header: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.md,
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
  },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  warn: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#FEF3C7",
    borderRadius: radius.md,
    padding: 12,
    marginBottom: spacing.md,
  },
  input: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: 12,
    marginTop: 6,
    minHeight: 48,
    fontSize: 15,
  },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
  },
  flattenRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surface,
    padding: 12,
    borderRadius: radius.md,
    marginTop: spacing.sm,
  },
  submit: {
    height: 52,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    marginTop: spacing.lg,
  },
  submitText: { color: "#fff", fontWeight: "700", marginLeft: 8, fontSize: 15 },
  successCard: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#D1FAE5",
    padding: 12,
    borderRadius: radius.md,
  },
});
