import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  Alert,
  Modal,
  StyleSheet,
  ActivityIndicator,
  Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import * as FileSystem from "expo-file-system";
import * as Sharing from "expo-sharing";
import { api, getToken } from "../api";
import { colors, spacing, radius, typography } from "../theme";

type Range = "day" | "week" | "month" | "all";

type Props = {
  template: any | null;
  onClose: () => void;
};

export default function StatsModal({ template, onClose }: Props) {
  const [range, setRange] = useState<Range>("month");
  const [stats, setStats] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);

  const params = (r: Range) => {
    const p: any = {};
    const now = new Date();
    if (r === "day") p.date_from = now.toISOString().slice(0, 10);
    else if (r === "week") {
      const f = new Date(now);
      f.setDate(f.getDate() - 7);
      p.date_from = f.toISOString().slice(0, 10);
    } else if (r === "month") {
      const f = new Date(now);
      f.setMonth(f.getMonth() - 1);
      p.date_from = f.toISOString().slice(0, 10);
    }
    return p;
  };

  const load = async (r: Range) => {
    if (!template) return;
    setRange(r);
    setStats(null);
    setBusy(true);
    try {
      const { data } = await api.get(`/forms/templates/${template.id}/stats`, { params: params(r) });
      setStats(data);
    } catch (e: any) {
      Alert.alert("Stats failed", e.response?.data?.detail || "Failed");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (template) load("month");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [template?.id]);

  const exportFile = async (format: "csv" | "pdf") => {
    if (!template) return;
    setExporting(format);
    try {
      const url = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api/forms/templates/${template.id}/stats/export`;
      const p = params(range);
      const qs = new URLSearchParams({ format, ...p }).toString();
      const fileUri = `${FileSystem.cacheDirectory}${template.title.replace(/\s+/g, "_")}-stats.${format}`;
      const token = await getToken();

      if (Platform.OS === "web") {
        // Open in new tab with token via fetch + blob
        const res = await fetch(`${url}?${qs}`, { headers: { Authorization: `Bearer ${token}` } });
        const blob = await res.blob();
        const dlUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = dlUrl;
        a.download = `${template.title}-stats.${format}`;
        a.click();
        URL.revokeObjectURL(dlUrl);
      } else {
        const dl = await FileSystem.downloadAsync(`${url}?${qs}`, fileUri, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (await Sharing.isAvailableAsync()) {
          await Sharing.shareAsync(dl.uri);
        } else {
          Alert.alert("Saved", `File saved to ${dl.uri}`);
        }
      }
    } catch (e: any) {
      Alert.alert("Export failed", e.message || "Failed");
    } finally {
      setExporting(null);
    }
  };

  return (
    <Modal visible={!!template} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={{ flex: 1, backgroundColor: "#fff" }}>
        <View style={s.header}>
          <TouchableOpacity onPress={onClose}>
            <Feather name="x" size={24} color={colors.primary} />
          </TouchableOpacity>
          <Text style={[typography.h3, { marginLeft: 12, flex: 1 }]} numberOfLines={1}>
            {template?.title} · Stats
          </Text>
        </View>

        <View style={{ flexDirection: "row", padding: spacing.md, gap: 6, flexWrap: "wrap" }}>
          {(["day", "week", "month", "all"] as Range[]).map((r) => (
            <TouchableOpacity
              key={r}
              testID={`range-${r}`}
              onPress={() => load(r)}
              style={[s.tab, range === r && s.tabActive]}
            >
              <Text style={[s.tabText, range === r && s.tabTextActive]}>{r}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={{ flexDirection: "row", paddingHorizontal: spacing.md, gap: 8, marginBottom: 8 }}>
          <TouchableOpacity
            testID="export-csv"
            style={[s.exportBtn, { backgroundColor: colors.primary }]}
            onPress={() => exportFile("csv")}
            disabled={!!exporting}
          >
            {exporting === "csv" ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <>
                <Feather name="download" size={14} color="#fff" />
                <Text style={s.exportText}>Export CSV</Text>
              </>
            )}
          </TouchableOpacity>
          <TouchableOpacity
            testID="export-pdf"
            style={[s.exportBtn, { backgroundColor: colors.brand }]}
            onPress={() => exportFile("pdf")}
            disabled={!!exporting}
          >
            {exporting === "pdf" ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <>
                <Feather name="file-text" size={14} color="#fff" />
                <Text style={s.exportText}>Export PDF</Text>
              </>
            )}
          </TouchableOpacity>
        </View>

        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm }}>
          {busy ? (
            <ActivityIndicator color={colors.brand} />
          ) : stats ? (
            <>
              <View style={s.card}>
                <Text style={typography.label}>Overall completion</Text>
                <Text style={{ fontSize: 38, fontWeight: "700", color: colors.primary, marginTop: 4 }}>
                  {stats.overall_percent}%
                </Text>
                <View style={s.bar}>
                  <View
                    style={{
                      width: `${Math.min(100, stats.overall_percent)}%`,
                      height: "100%",
                      backgroundColor: stats.on_target ? colors.success : colors.alert,
                    }}
                  />
                </View>
                <Text style={[typography.small, { marginTop: 6 }]}>
                  {stats.overall_done}/{stats.overall_possible} sub-tasks done across {stats.submissions} submissions · target {stats.target_percent || 100}%
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
                  <View key={it.id} style={s.card}>
                    <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                      <Text style={{ fontWeight: "700", color: colors.primary }}>{it.label}</Text>
                      <Text
                        style={{
                          fontWeight: "700",
                          color: pct >= (stats.target_percent || 100) ? colors.success : colors.alert,
                        }}
                      >
                        {pct}%
                      </Text>
                    </View>
                    <View style={{ flexDirection: "row", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
                      {it.sub_keys.map((sk: string) => (
                        <View key={sk} style={s.subPill}>
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
  );
}

const s = StyleSheet.create({
  header: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.md,
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
  },
  tab: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.pill, backgroundColor: colors.surface },
  tabActive: { backgroundColor: colors.primary },
  tabText: { color: colors.textSecondary, fontWeight: "600", fontSize: 13, textTransform: "capitalize" },
  tabTextActive: { color: "#fff" },
  exportBtn: {
    flex: 1,
    flexDirection: "row",
    height: 40,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
  },
  exportText: { color: "#fff", fontWeight: "700", fontSize: 13 },
  card: {
    backgroundColor: "#fff",
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 14,
  },
  bar: {
    height: 8,
    backgroundColor: colors.surface,
    borderRadius: 4,
    marginTop: 8,
    overflow: "hidden",
  },
  subPill: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
  },
});
