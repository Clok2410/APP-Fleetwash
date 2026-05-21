// Staff HR Sign Modal — view PDF, mark read, draw signature, submit.
// Used in (tabs)/forms.tsx or anywhere the staff needs to sign issued HR documents.
import React, { useEffect, useState, useCallback } from "react";
import { Modal, View, Text, TouchableOpacity, ScrollView, Alert, StyleSheet, Platform, TextInput, ActivityIndicator } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { api } from "../api";
import { colors, radius, spacing, typography } from "../theme";
import SignaturePad from "./SignaturePad";

type Props = {
  visible: boolean;
  issuanceId: string | null;
  onClose: () => void;
  onSigned?: () => void;
};

export default function HRSignModal({ visible, issuanceId, onClose, onSigned }: Props) {
  const [issuance, setIssuance] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [hasRead, setHasRead] = useState(false);
  const [showSig, setShowSig] = useState(false);
  const [printedName, setPrintedName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [signatureB64, setSignatureB64] = useState<string | null>(null);
  const [docOpen, setDocOpen] = useState(false);
  const [docPdfB64, setDocPdfB64] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!issuanceId) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/hr/issuances/${issuanceId}`);
      setIssuance(data);
      // pre-fill printed name if staff name available
      if (!printedName) setPrintedName(data.user_name || "");
    } catch (e: any) {
      Alert.alert("Failed", e.response?.data?.detail || "Could not load issuance");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [issuanceId]);

  useEffect(() => {
    if (visible && issuanceId) {
      load();
    } else {
      setIssuance(null);
      setHasRead(false);
      setShowSig(false);
      setSignatureB64(null);
      setPrintedName("");
      setDocOpen(false);
      setDocPdfB64(null);
    }
  }, [visible, issuanceId, load]);

  const markRead = async () => {
    if (!issuance) return;
    try {
      const { data } = await api.post(`/hr/issuances/${issuance.id}/read`);
      setIssuance(data);
      setHasRead(true);
    } catch (e: any) {
      Alert.alert("Failed", e.response?.data?.detail || "Could not mark read");
    }
  };

  const openDocument = async () => {
    if (!issuance) return;
    // Fetch the template's pdf_base64 once for in-app preview
    try {
      if (!docPdfB64) {
        const { data } = await api.get(`/pdf-forms/templates/${issuance.template_id}`);
        setDocPdfB64(data?.pdf_base64 || null);
      }
      setDocOpen(true);
    } catch (e: any) {
      Alert.alert("Failed", "Could not load PDF preview");
    }
  };

  const handleSignatureSaved = (b64: string) => {
    setSignatureB64(b64);
    setShowSig(false);
  };

  const submitSign = async () => {
    if (!issuance || !signatureB64) {
      Alert.alert("Sign first", "Please draw your signature before submitting.");
      return;
    }
    if (!hasRead) {
      Alert.alert("Please confirm read", "Tick 'I have read this document' before signing.");
      return;
    }
    setSubmitting(true);
    try {
      await api.post(`/hr/issuances/${issuance.id}/sign`, {
        signature_base64: signatureB64,
        printed_name: printedName,
      });
      Alert.alert("Signed", "Your signed document has been saved.");
      onSigned && onSigned();
      onClose();
    } catch (e: any) {
      Alert.alert("Failed", e.response?.data?.detail || "Could not submit signature");
    } finally {
      setSubmitting(false);
    }
  };

  if (!issuance) {
    return (
      <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
        <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }}>
          <View style={styles.header}>
            <TouchableOpacity onPress={onClose} style={styles.closeBtn} testID="hrsign-close">
              <Feather name="x" size={20} color={colors.primary} />
            </TouchableOpacity>
            <Text style={typography.h2}>HR Document</Text>
          </View>
          <View style={{ padding: spacing.lg, alignItems: "center" }}>
            {loading ? <ActivityIndicator color={colors.brand} /> : <Text style={typography.small}>—</Text>}
          </View>
        </SafeAreaView>
      </Modal>
    );
  }

  const isSigned = issuance.status === "signed";
  const isCancelled = issuance.status === "cancelled";
  const isExpired = issuance.status === "expired";
  const locked = isSigned || isCancelled || isExpired;

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }}>
        <View style={styles.header}>
          <TouchableOpacity onPress={onClose} style={styles.closeBtn} testID="hrsign-close">
            <Feather name="x" size={20} color={colors.primary} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={typography.h2}>{issuance.template_title}</Text>
            <Text style={typography.small}>
              Issued by {issuance.issued_by_name} · {new Date(issuance.issued_at).toLocaleDateString()}
            </Text>
          </View>
          <View
            style={[
              styles.statusPill,
              {
                backgroundColor: isSigned
                  ? "#0F766E"
                  : isCancelled || isExpired
                  ? colors.alert
                  : colors.brand,
              },
            ]}
          >
            <Text style={{ color: "#fff", fontWeight: "800", fontSize: 10 }}>
              {issuance.status?.toUpperCase()}
            </Text>
          </View>
        </View>

        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}>
          {/* Message + expiry */}
          {issuance.message ? (
            <View style={styles.card}>
              <Text style={typography.label}>Message from admin</Text>
              <Text style={{ marginTop: 4 }}>{issuance.message}</Text>
            </View>
          ) : null}

          {issuance.expires_at ? (
            <View style={[styles.card, { backgroundColor: "#FEF3C7", borderColor: "#FDE68A" }]}>
              <Text style={[typography.small, { fontWeight: "700" }]}>
                <Feather name="clock" size={12} color="#92400E" /> Expires {issuance.expires_at}
              </Text>
            </View>
          ) : null}

          {/* Step 1: Read */}
          <View style={styles.card}>
            <Text style={typography.label}>Step 1 · Read the document</Text>
            <TouchableOpacity testID="hrsign-open-doc" onPress={openDocument} style={styles.viewBtn}>
              <Feather name="file-text" size={14} color="#fff" />
              <Text style={styles.viewBtnText}>Open PDF</Text>
            </TouchableOpacity>

            <TouchableOpacity
              testID="hrsign-read"
              style={styles.checkbox}
              disabled={locked}
              onPress={async () => {
                const next = !hasRead;
                setHasRead(next);
                if (next && !issuance.read_at && !locked) {
                  await markRead();
                }
              }}
            >
              <View style={[styles.checkboxBox, hasRead && styles.checkboxBoxChecked]}>
                {hasRead ? <Feather name="check" size={14} color="#fff" /> : null}
              </View>
              <Text style={{ flex: 1, marginLeft: 8, color: colors.primary, fontWeight: "600", fontSize: 13 }}>
                I have read and understood this document
              </Text>
            </TouchableOpacity>
            {issuance.read_at ? (
              <Text style={[typography.small, { color: "#0F766E", marginTop: 4 }]}>
                <Feather name="check-circle" size={11} color="#0F766E" /> Read confirmation recorded {new Date(issuance.read_at).toLocaleString()}
              </Text>
            ) : null}
          </View>

          {/* Step 2: Sign */}
          <View style={styles.card}>
            <Text style={typography.label}>Step 2 · Sign</Text>
            {isSigned ? (
              <Text style={[typography.small, { color: "#0F766E", marginTop: 4 }]}>
                <Feather name="check-circle" size={12} color="#0F766E" /> Signed by {issuance.printed_name || issuance.user_name} on{" "}
                {new Date(issuance.signed_at).toLocaleString()}
              </Text>
            ) : (
              <>
                <Text style={[typography.small, { marginTop: 4 }]}>Printed name</Text>
                <TextInput
                  testID="hrsign-name"
                  value={printedName}
                  onChangeText={setPrintedName}
                  placeholder="Your full name"
                  placeholderTextColor={colors.textMuted}
                  editable={!locked}
                  style={styles.input}
                />
                {signatureB64 ? (
                  <View style={{ marginTop: 8 }}>
                    <Text style={[typography.small, { color: "#0F766E", fontWeight: "700" }]}>
                      <Feather name="check" size={11} color="#0F766E" /> Signature ready
                    </Text>
                    <TouchableOpacity onPress={() => setShowSig(true)} style={{ marginTop: 6 }}>
                      <Text style={{ color: colors.brand, fontWeight: "700", fontSize: 12 }}>Redraw signature</Text>
                    </TouchableOpacity>
                  </View>
                ) : (
                  <TouchableOpacity
                    testID="hrsign-open-pad"
                    style={[styles.signBtn, !hasRead && { opacity: 0.5 }]}
                    disabled={!hasRead || locked}
                    onPress={() => setShowSig(true)}
                  >
                    <Feather name="edit-3" size={14} color="#fff" />
                    <Text style={styles.signBtnText}>Draw signature</Text>
                  </TouchableOpacity>
                )}
                {!hasRead && (
                  <Text style={[typography.small, { marginTop: 6, fontStyle: "italic" }]}>
                    Confirm you have read the document above first.
                  </Text>
                )}
              </>
            )}
          </View>

          {!locked && (
            <TouchableOpacity
              testID="hrsign-submit"
              onPress={submitSign}
              disabled={submitting || !signatureB64 || !hasRead}
              style={[styles.submitBtn, (!signatureB64 || !hasRead) && { opacity: 0.45 }]}
            >
              {submitting ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <>
                  <Feather name="check-circle" size={16} color="#fff" />
                  <Text style={{ color: "#fff", fontWeight: "800", marginLeft: 6 }}>Submit signed document</Text>
                </>
              )}
            </TouchableOpacity>
          )}
        </ScrollView>

        {/* Signature pad sub-modal */}
        <Modal visible={showSig} animationType="slide" transparent onRequestClose={() => setShowSig(false)}>
          <View style={styles.subBg}>
            <View style={styles.subCard}>
              <Text style={typography.h3}>Sign here</Text>
              <Text style={[typography.small, { marginBottom: 8 }]}>
                Your signature will be stamped with your name + current date on the document.
              </Text>
              <SignaturePad onSave={handleSignatureSaved} onCancel={() => setShowSig(false)} height={220} />
            </View>
          </View>
        </Modal>

        {/* PDF preview sub-modal */}
        <Modal visible={docOpen} animationType="slide" onRequestClose={() => setDocOpen(false)}>
          <SafeAreaView style={{ flex: 1, backgroundColor: "#000" }}>
            <View style={[styles.header, { backgroundColor: "#000", borderBottomColor: "#222" }]}>
              <TouchableOpacity onPress={() => setDocOpen(false)} style={[styles.closeBtn, { backgroundColor: "#1F2937" }]}>
                <Feather name="x" size={20} color="#fff" />
              </TouchableOpacity>
              <Text style={[typography.h3, { color: "#fff" }]}>{issuance.template_title}</Text>
            </View>
            {Platform.OS === "web" ? (
              docPdfB64 ? (
                // @ts-ignore
                <iframe
                  src={`data:application/pdf;base64,${docPdfB64}`}
                  style={{ width: "100%", height: "100%", border: "none" }}
                  title="HR document"
                />
              ) : (
                <View style={{ flex: 1, justifyContent: "center", alignItems: "center" }}>
                  <ActivityIndicator color="#fff" />
                </View>
              )
            ) : (
              <View style={{ flex: 1, justifyContent: "center", alignItems: "center", padding: 20 }}>
                <Feather name="file-text" size={48} color="#fff" />
                <Text style={{ color: "#fff", marginTop: 12, textAlign: "center" }}>
                  PDF preview is best viewed on web. Use your device's PDF viewer to open the file separately.
                </Text>
              </View>
            )}
          </SafeAreaView>
        </Modal>
      </SafeAreaView>
    </Modal>
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
  statusPill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  card: {
    backgroundColor: "#fff",
    borderRadius: radius.lg,
    padding: 14,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: colors.border,
  },
  viewBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    height: 40,
    paddingHorizontal: 14,
    backgroundColor: colors.brand,
    borderRadius: 999,
    gap: 6,
    marginTop: 8,
    alignSelf: "flex-start",
  },
  viewBtnText: { color: "#fff", fontWeight: "700", fontSize: 13 },
  checkbox: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 12,
    paddingVertical: 4,
  },
  checkboxBox: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#fff",
  },
  checkboxBoxChecked: { backgroundColor: colors.brand, borderColor: colors.brand },
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
  signBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    height: 44,
    paddingHorizontal: 16,
    backgroundColor: colors.primary,
    borderRadius: 999,
    gap: 6,
    marginTop: 10,
  },
  signBtnText: { color: "#fff", fontWeight: "700" },
  submitBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    height: 50,
    paddingHorizontal: 24,
    backgroundColor: "#0F766E",
    borderRadius: 999,
    gap: 6,
    marginTop: 10,
  },
  subBg: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.5)" },
  subCard: {
    backgroundColor: "#fff",
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: spacing.lg,
  },
});
