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
import { useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { SafeAreaView } from "react-native-safe-area-context";
import * as DocumentPicker from "expo-document-picker";
import * as FileSystem from "expo-file-system";
import { api } from "../../src/api";
import { useAuth } from "../../src/auth";
import { colors, spacing, radius, typography } from "../../src/theme";
import { readAssetAsBase64 } from "../../src/utils/fileToBase64";
import WebDropZone from "../../src/components/WebDropZone";
import PdfFormFillModal from "../../src/components/PdfFormFillModal";

export default function DriveScreen() {
  const { user } = useAuth();
  const [stack, setStack] = useState<{ id: string | null; name: string }[]>([{ id: null, name: "Drive" }]);
  const [folders, setFolders] = useState<any[]>([]);
  const [files, setFiles] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [newFolder, setNewFolder] = useState(false);
  const [folderName, setFolderName] = useState("");
  const [previewFile, setPreviewFile] = useState<any>(null);
  const [activeFillSession, setActiveFillSession] = useState<string | null>(null);
  const [fillBusy, setFillBusy] = useState(false);

  const currentFolder = stack[stack.length - 1];

  const load = useCallback(async () => {
    try {
      const [f, files] = await Promise.all([
        api.get("/drive/folders", { params: { parent_id: currentFolder.id || undefined } }),
        api.get("/drive/files", { params: { folder_id: currentFolder.id || undefined } }),
      ]);
      setFolders(f.data);
      setFiles(files.data);
    } catch {}
  }, [currentFolder.id]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const open = (f: any) => setStack([...stack, { id: f.id, name: f.name }]);
  const goBack = () => stack.length > 1 && setStack(stack.slice(0, -1));

  const createFolder = async () => {
    if (!folderName.trim()) return;
    try {
      await api.post("/drive/folders", { name: folderName.trim(), parent_id: currentFolder.id });
      setFolderName("");
      setNewFolder(false);
      await load();
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Failed");
    }
  };

  const uploadFile = async () => {
    try {
      const res = await DocumentPicker.getDocumentAsync({
        type: "*/*",
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (res.canceled) return;
      const asset: any = res.assets[0];
      if ((asset.size || 0) > 10 * 1024 * 1024) {
        Alert.alert("Too large", "Max 10MB per file");
        return;
      }
      const b64 = await readAssetAsBase64(asset, FileSystem);
      if (!b64) {
        Alert.alert("Upload failed", "Could not read file. Try a different file.");
        return;
      }
      await api.post("/drive/files", {
        name: asset.name,
        folder_id: currentFolder.id,
        mime_type: asset.mimeType || "application/octet-stream",
        data_base64: b64,
        size: asset.size,
      });
      await load();
      Alert.alert("Uploaded", asset.name);
    } catch (e: any) {
      Alert.alert("Upload failed", e.response?.data?.detail || e.message);
    }
  };

  const uploadDroppedFile = async (file: File) => {
    try {
      if ((file.size || 0) > 10 * 1024 * 1024) {
        Alert.alert("Too large", "Max 10MB per file");
        return;
      }
      const b64 = await readAssetAsBase64({ file, uri: "" }, FileSystem);
      if (!b64) {
        Alert.alert("Upload failed", "Could not read file.");
        return;
      }
      await api.post("/drive/files", {
        name: file.name,
        folder_id: currentFolder.id,
        mime_type: file.type || "application/octet-stream",
        data_base64: b64,
        size: file.size,
      });
      await load();
      Alert.alert("Uploaded", file.name);
    } catch (e: any) {
      Alert.alert("Upload failed", e.response?.data?.detail || e.message);
    }
  };

  const fillPdfFromDrive = async (driveFile: any) => {
    if (fillBusy) return;
    setFillBusy(true);
    try {
      // 1) Promote/reuse this drive file as a PDF Form template
      const { data: tpl } = await api.post(`/drive/files/${driveFile.id}/as-pdf-form`);
      if (!tpl?.has_acroform) {
        Alert.alert(
          "No fillable fields",
          "This PDF doesn't have any AcroForm fields. You can still preview / download it.",
        );
        return;
      }
      // 2) Reuse existing draft session if any (collab), else create new
      const { data: sessions } = await api.get(`/pdf-forms/sessions`, {
        params: { template_id: tpl.id, status: "draft" },
      });
      let sess = (sessions || [])[0];
      if (!sess) {
        const { data } = await api.post(`/pdf-forms/templates/${tpl.id}/sessions`, {
          name: driveFile.name?.replace(/\.pdf$/i, "") || "Form",
        });
        sess = data;
      }
      setPreviewFile(null);
      setActiveFillSession(sess.id);
    } catch (e: any) {
      Alert.alert("Could not open form", e.response?.data?.detail || e.message);
    } finally {
      setFillBusy(false);
    }
  };

  const deleteFile = async (id: string) => {
    Alert.alert("Delete file?", "This cannot be undone.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: async () => {
          await api.delete(`/drive/files/${id}`);
          await load();
        },
      },
    ]);
  };

  const showPreview = async (f: any) => {
    try {
      const { data } = await api.get(`/drive/files/${f.id}`);
      setPreviewFile(data);
    } catch {}
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <View style={styles.header}>
        <View style={{ flexDirection: "row", alignItems: "center" }}>
          {stack.length > 1 && (
            <TouchableOpacity onPress={goBack} style={styles.backBtn}>
              <Feather name="arrow-left" size={20} color={colors.primary} />
            </TouchableOpacity>
          )}
          <View>
            <Text style={typography.label}>Shared Drive</Text>
            <Text style={typography.h2}>{currentFolder.name}.</Text>
          </View>
        </View>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <TouchableOpacity testID="new-folder-btn" style={styles.iconBtn} onPress={() => setNewFolder(true)}>
            <Feather name="folder-plus" size={18} color={colors.primary} />
          </TouchableOpacity>
          <TouchableOpacity testID="upload-file-btn" style={[styles.iconBtn, { backgroundColor: colors.primary }]} onPress={uploadFile}>
            <Feather name="upload" size={18} color="#fff" />
          </TouchableOpacity>
        </View>
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
        <WebDropZone
          onFile={uploadDroppedFile}
          style={{ marginBottom: 12, paddingVertical: 16 } as any}
        >
          <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "center" }}>
            <Feather name="upload-cloud" size={16} color={colors.primary} />
            <Text style={[typography.small, { marginLeft: 8, color: colors.primary, fontWeight: "600" }]}>
              Drag &amp; drop a file here, or use the upload button
            </Text>
          </View>
        </WebDropZone>

        {folders.length === 0 && files.length === 0 && (
          <View style={styles.empty}>
            <Feather name="folder" size={28} color={colors.textMuted} />
            <Text style={[typography.body, { textAlign: "center", marginTop: 10 }]}>
              Empty folder. Tap upload or create a new folder.
            </Text>
          </View>
        )}
        {folders.map((f) => (
          <TouchableOpacity key={f.id} style={styles.row} onPress={() => open(f)} testID={`folder-${f.id}`}>
            <View style={[styles.iconWrap, { backgroundColor: colors.brandSoft }]}>
              <Feather name="folder" size={18} color={colors.brand} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle}>{f.name}</Text>
              <Text style={typography.small}>by {f.owner_name}</Text>
            </View>
            <Feather name="chevron-right" size={18} color={colors.textMuted} />
          </TouchableOpacity>
        ))}
        {files.map((f) => {
          const isPdf = (f.mime_type || "").includes("pdf") || (f.name || "").toLowerCase().endsWith(".pdf");
          return (
            <TouchableOpacity key={f.id} style={styles.row} onPress={() => showPreview(f)} testID={`file-${f.id}`}>
              <View style={[styles.iconWrap, { backgroundColor: isPdf ? "#FEE2E2" : colors.surface }]}>
                <Feather name={isPdf ? "file-text" : "file"} size={18} color={isPdf ? "#B91C1C" : colors.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>{f.name}</Text>
                <Text style={typography.small}>
                  {(f.size / 1024).toFixed(1)} KB · {f.owner_name}
                </Text>
              </View>
              {isPdf ? (
                <TouchableOpacity
                  testID={`fill-${f.id}`}
                  style={styles.fillBtn}
                  onPress={(e: any) => {
                    if (e?.stopPropagation) e.stopPropagation();
                    fillPdfFromDrive(f);
                  }}
                >
                  <Feather name="edit-3" size={12} color="#fff" />
                  <Text style={styles.fillBtnText}>Fill</Text>
                </TouchableOpacity>
              ) : null}
              <TouchableOpacity onPress={() => deleteFile(f.id)} style={{ padding: 6 }}>
                <Feather name="trash-2" size={16} color={colors.alert} />
              </TouchableOpacity>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <Modal visible={newFolder} animationType="slide" transparent onRequestClose={() => setNewFolder(false)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <Text style={typography.h3}>New Folder</Text>
            <TextInput
              style={styles.input}
              placeholder="Folder name"
              value={folderName}
              onChangeText={setFolderName}
              placeholderTextColor={colors.textMuted}
              autoFocus
            />
            <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
              <TouchableOpacity style={[styles.btn, styles.btnGhost]} onPress={() => setNewFolder(false)}>
                <Text style={styles.btnGhostText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="create-folder-submit" style={[styles.btn, styles.btnPrimary]} onPress={createFolder}>
                <Text style={styles.btnPrimaryText}>Create</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      <Modal visible={!!previewFile} animationType="slide" onRequestClose={() => setPreviewFile(null)}>
        <SafeAreaView style={{ flex: 1, backgroundColor: "#000" }}>
          <View style={styles.previewHeader}>
            <Text style={{ color: "#fff", flex: 1, fontWeight: "600" }} numberOfLines={1}>
              {previewFile?.name}
            </Text>
            <TouchableOpacity onPress={() => setPreviewFile(null)}>
              <Feather name="x" size={24} color="#fff" />
            </TouchableOpacity>
          </View>
          <ScrollView contentContainerStyle={{ padding: 16 }}>
            <Text style={{ color: "#fff", marginBottom: 8 }}>
              MIME: {previewFile?.mime_type}
            </Text>
            <Text style={{ color: "#9ca3af", marginBottom: 16 }}>
              Size: {((previewFile?.size || 0) / 1024).toFixed(1)} KB
            </Text>
            {(previewFile?.mime_type?.includes("pdf") || (previewFile?.name || "").toLowerCase().endsWith(".pdf")) ? (
              <>
                <TouchableOpacity
                  testID="preview-fill-btn"
                  style={[styles.btn, { backgroundColor: colors.success, marginBottom: 12, flexDirection: "row", justifyContent: "center" }]}
                  onPress={() => fillPdfFromDrive(previewFile)}
                  disabled={fillBusy}
                >
                  <Feather name="edit-3" size={16} color="#fff" />
                  <Text style={[styles.btnPrimaryText, { marginLeft: 8 }]}>
                    {fillBusy ? "Opening…" : "Fill as Form"}
                  </Text>
                </TouchableOpacity>
                {Platform.OS === "web" && previewFile?.data_base64 ? (
                  <View style={{ height: 480, backgroundColor: "#fff", borderRadius: 8, overflow: "hidden" }}>
                    {/* @ts-ignore web-only iframe */}
                    <iframe
                      src={`data:application/pdf;base64,${previewFile.data_base64}`}
                      style={{ width: "100%", height: "100%", border: 0 }}
                      title={previewFile.name}
                    />
                  </View>
                ) : (
                  <View style={styles.imgWrap}>
                    <Feather name="file-text" size={48} color="#fff" />
                    <Text style={{ color: "#fff", marginTop: 12 }}>
                      Tap "Fill as Form" to open and complete this PDF.
                    </Text>
                  </View>
                )}
              </>
            ) : previewFile?.mime_type?.startsWith("image/") && previewFile?.data_base64 ? (
              <View style={styles.imgWrap}>
                <Text style={{ color: "#fff" }}>
                  📎 Image previewed in-app. Use Save to share.
                </Text>
              </View>
            ) : (
              <View style={styles.imgWrap}>
                <Feather name="file-text" size={48} color="#fff" />
                <Text style={{ color: "#fff", marginTop: 12 }}>
                  File ready. Stored securely in your shared drive.
                </Text>
              </View>
            )}
          </ScrollView>
        </SafeAreaView>
      </Modal>

      <PdfFormFillModal
        templateId={null}
        sessionId={activeFillSession}
        isAdmin={user?.role === "admin"}
        onClose={async () => {
          setActiveFillSession(null);
          await load();
        }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  fillBtn: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.success,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.pill,
    marginRight: 6,
  },
  fillBtnText: { color: "#fff", fontWeight: "700", fontSize: 11, marginLeft: 4 },
  header: {
    padding: spacing.lg,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  backBtn: { marginRight: 8, padding: 4 },
  iconBtn: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
  },
  list: { padding: spacing.lg, paddingTop: 0, gap: spacing.sm },
  row: {
    backgroundColor: "#fff",
    borderRadius: radius.lg,
    padding: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderWidth: 1,
    borderColor: colors.border,
  },
  iconWrap: { width: 40, height: 40, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  rowTitle: { fontSize: 15, fontWeight: "600", color: colors.primary },
  empty: { padding: spacing.xl, alignItems: "center" },
  modalBg: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.4)" },
  modalCard: {
    backgroundColor: "#fff",
    padding: spacing.lg,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
  },
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
  previewHeader: {
    flexDirection: "row",
    alignItems: "center",
    padding: 16,
    borderBottomColor: "#222",
    borderBottomWidth: 1,
  },
  imgWrap: {
    backgroundColor: "#111",
    padding: 24,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 240,
  },
});
