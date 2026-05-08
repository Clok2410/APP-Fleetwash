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
import { useFocusEffect, useRouter, Redirect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { SafeAreaView } from "react-native-safe-area-context";
import { Linking, Platform } from "react-native";
import { api } from "../src/api";
import { useAuth } from "../src/auth";
import { colors, spacing, radius, typography } from "../src/theme";
import FormBuilderModal from "../src/components/FormBuilderModal";
import StatsModal from "../src/components/StatsModal";
import OffsiteMap from "../src/components/OffsiteMap";
import CustomerModal from "../src/components/CustomerModal";
import WebDropZone from "../src/components/WebDropZone";
import { Calendar } from "react-native-calendars";

export default function AdminScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const [tab, setTab] = useState<"holidays" | "shifts" | "forms" | "pdf-forms" | "users" | "depots" | "offsite" | "customers">("holidays");
  const [holidays, setHolidays] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [allShifts, setAllShifts] = useState<any[]>([]);
  const [allTemplates, setAllTemplates] = useState<any[]>([]);
  const [pdfTemplates, setPdfTemplates] = useState<any[]>([]);
  const [pdfUploading, setPdfUploading] = useState(false);
  const [pdfTitle, setPdfTitle] = useState("");
  const [pdfDesc, setPdfDesc] = useState("");
  const [pdfPicked, setPdfPicked] = useState<{ name: string; base64: string } | null>(null);
  const [pdfModalOpen, setPdfModalOpen] = useState(false);
  const [depots, setDepots] = useState<any[]>([]);
  const [offsite, setOffsite] = useState<any[]>([]);
  const [customers, setCustomers] = useState<any[]>([]);
  const [activeCustomerId, setActiveCustomerId] = useState<string | null>(null);
  const [newCustomerModal, setNewCustomerModal] = useState(false);
  const [ncName, setNcName] = useState("");
  const [ncCompany, setNcCompany] = useState("");
  const [ncEmail, setNcEmail] = useState("");
  const [ncPhone, setNcPhone] = useState("");
  const [offDepot, setOffDepot] = useState<string>("");
  const [offUser, setOffUser] = useState<string>("");
  const [offFrom, setOffFrom] = useState<string>("");
  const [offTo, setOffTo] = useState<string>("");
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
  const [sCustomerId, setSCustomerId] = useState("");
  const [sSiteId, setSSiteId] = useState("");
  const [sRecurring, setSRecurring] = useState<"none" | "daily" | "weekly">("none");
  const [sRepeat, setSRepeat] = useState("4");
  const [swaps, setSwaps] = useState<any[]>([]);
  const [availability, setAvailability] = useState<any[]>([]);
  const [entUser, setEntUser] = useState<any>(null);
  const [entValue, setEntValue] = useState("25");
  const [editShift, setEditShift] = useState<any>(null);
  const [eTitle, setETitle] = useState("");
  const [eStart, setEStart] = useState("");
  const [eEnd, setEEnd] = useState("");
  const [eLoc, setELoc] = useState("");
  const [eUser, setEUser] = useState("");

  const [formModal, setFormModal] = useState(false);
  const [statsTpl, setStatsTpl] = useState<any>(null);

  const [userModal, setUserModal] = useState(false);
  const [uEmail, setUEmail] = useState("");
  const [uName, setUName] = useState("");
  const [uPass, setUPass] = useState("");
  const [uRole, setURole] = useState<"staff" | "admin">("staff");

  const load = useCallback(async () => {
    try {
      const offsiteParams: any = {};
      if (offDepot) offsiteParams.depot_id = offDepot;
      if (offUser) offsiteParams.user_id = offUser;
      if (offFrom) offsiteParams.date_from = offFrom;
      if (offTo) offsiteParams.date_to = offTo;
      const [h, u, s, t, d, o, cust, pft, sw, av] = await Promise.all([
        api.get("/holidays/requests", { params: { all: true } }),
        api.get("/users"),
        api.get("/shifts", { params: { all: true } }),
        api.get("/forms/templates"),
        api.get("/depots"),
        api.get("/admin/off-site-clock-ins", { params: offsiteParams }).catch(() => ({ data: [] })),
        api.get("/customers").catch(() => ({ data: [] })),
        api.get("/pdf-forms/templates").catch(() => ({ data: [] })),
        api.get("/shifts/swaps").catch(() => ({ data: [] })),
        api.get("/availability", { params: { all: true } }).catch(() => ({ data: [] })),
      ]);
      setHolidays(h.data);
      setUsers(u.data);
      setAllShifts(s.data);
      setAllTemplates(t.data);
      setDepots(d.data);
      setOffsite(o.data || []);
      setCustomers(cust.data || []);
      setPdfTemplates(pft.data || []);
      setSwaps(sw.data || []);
      setAvailability(av.data || []);
    } catch {}
  }, [offDepot, offUser, offFrom, offTo]);

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
      const bundleSummary = (data.bundles || [])
        .map((b: any) => `• ${b.depot_name}: ${b.filename}`)
        .join("\n") || "(no bundles)";
      Alert.alert(
        "Digest generated",
        `${data.mocked ? "MOCKED — no RESEND_API_KEY set." : "Sent."}\nRecipients: ${(data.recipients || []).join(", ")}\n\n${bundleSummary}`
      );
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Failed");
    } finally {
      setDigestBusy(false);
    }
  };

  // Role guard placed AFTER all hooks to comply with Rules of Hooks
  if (user && user.role !== "admin") {
    return <Redirect href="/(tabs)/home" />;
  }

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
      const { data } = await api.post("/shifts", {
        user_id: sUser,
        title: sTitle,
        start: sStart,
        end: sEnd,
        location: sLoc,
        customer_id: sCustomerId || undefined,
        site_id: sSiteId || undefined,
        recurring: sRecurring,
        repeat_count: sRecurring === "none" ? 1 : Math.max(1, Math.min(60, parseInt(sRepeat || "1", 10) || 1)),
      });
      setShiftModal(false);
      setSUser(""); setSTitle(""); setSStart(""); setSEnd(""); setSLoc("");
      setSCustomerId(""); setSSiteId("");
      setSRecurring("none"); setSRepeat("4");
      await load();
      if ((data?.created || 0) > 1) {
        Alert.alert("Series created", `Generated ${data.created} shifts (${sRecurring}).`);
      }
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Failed");
    }
  };

  const decideSwap = async (id: string, decision: "approved" | "rejected") => {
    try {
      await api.post(`/shifts/swaps/${id}/decision`, null, { params: { decision } });
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

  const pickPdf = async () => {
    try {
      const DocumentPicker = await import("expo-document-picker");
      const FileSystem = await import("expo-file-system");
      const res: any = await DocumentPicker.getDocumentAsync({
        type: "application/pdf",
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (res.canceled || !res.assets || res.assets.length === 0) return;
      const file = res.assets[0];
      const base64 = await readAssetAsBase64(file, FileSystem);
      if (!base64) {
        Alert.alert("Pick failed", "Could not read PDF contents from picker.");
        return;
      }
      setPdfPicked({ name: file.name || "form.pdf", base64 });
      if (!pdfTitle) setPdfTitle((file.name || "form.pdf").replace(/\.pdf$/i, ""));
    } catch (e: any) {
      Alert.alert("Pick failed", String(e?.message || e));
    }
  };

  const onWebDrop = async (file: File) => {
    try {
      const ab = await file.arrayBuffer();
      const bytes = new Uint8Array(ab);
      let binary = "";
      for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
      const base64 = btoa(binary);
      setPdfPicked({ name: file.name || "form.pdf", base64 });
      if (!pdfTitle) setPdfTitle((file.name || "form.pdf").replace(/\.pdf$/i, ""));
      setPdfModalOpen(true);
    } catch (e: any) {
      Alert.alert("Drop failed", String(e?.message || e));
    }
  };

  const uploadPdfTemplate = async () => {
    if (!pdfPicked) return Alert.alert("Pick a PDF first");
    if (!pdfTitle) return Alert.alert("Title required");
    setPdfUploading(true);
    try {
      const { data } = await api.post("/pdf-forms/templates", {
        title: pdfTitle,
        description: pdfDesc,
        pdf_base64: pdfPicked.base64,
      });
      setPdfModalOpen(false);
      setPdfPicked(null);
      setPdfTitle("");
      setPdfDesc("");
      await load();
      if (data.has_acroform) {
        Alert.alert("Uploaded", `Detected ${data.field_count} fillable fields.`);
      } else {
        Alert.alert("Uploaded", "No AcroForm fields were detected. Staff can still view it but not fill it.");
      }
    } catch (e: any) {
      Alert.alert("Upload failed", e.response?.data?.detail || "Try again");
    } finally {
      setPdfUploading(false);
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
        {(["holidays", "shifts", "forms", "pdf-forms", "users", "depots", "offsite", "customers"] as const).map((t) => (
          <TouchableOpacity
            key={t}
            testID={`admin-tab-${t}`}
            onPress={() => setTab(t)}
            style={[styles.tab, tab === t && styles.tabActive]}
          >
            <Text style={[styles.tabText, tab === t && styles.tabTextActive]}>
              {t === "offsite"
                ? `off-site${offsite.length ? ` · ${offsite.length}` : ""}`
                : t === "pdf-forms"
                ? "PDF"
                : t}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView contentContainerStyle={styles.list}>
        {tab === "holidays" && (
          <>
            {/* Team Holiday Calendar */}
            <Text style={[typography.label, { marginBottom: 6 }]}>Team Holiday Calendar</Text>
            <View style={{ borderRadius: radius.lg, overflow: "hidden", borderWidth: 1, borderColor: colors.border, backgroundColor: "#fff" }}>
              <Calendar
                testID="admin-holiday-calendar"
                markingType="multi-dot"
                markedDates={(() => {
                  const m: any = {};
                  const palette = ["#10B981", "#F59E0B", "#3B82F6", "#EC4899", "#8B5CF6", "#EF4444"];
                  const userColor: Record<string, string> = {};
                  let idx = 0;
                  holidays.forEach((h) => {
                    if (h.status === "rejected") return;
                    if (!userColor[h.user_id]) {
                      userColor[h.user_id] = palette[idx % palette.length];
                      idx += 1;
                    }
                    const c = userColor[h.user_id];
                    try {
                      const sD = new Date(h.start_date);
                      const eD = new Date(h.end_date);
                      const cur = new Date(sD);
                      while (cur <= eD) {
                        const ds = cur.toISOString().slice(0, 10);
                        if (!m[ds]) m[ds] = { dots: [] };
                        m[ds].dots.push({
                          color: h.status === "approved" ? c : "#FBBF24",
                          key: `${h.id}-${ds}`,
                        });
                        cur.setDate(cur.getDate() + 1);
                      }
                    } catch {}
                  });
                  return m;
                })()}
                theme={{ todayTextColor: colors.brand, arrowColor: colors.primary }}
              />
            </View>
            <View style={{ flexDirection: "row", alignItems: "center", marginTop: 6, gap: 12 }}>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: "#10B981", marginRight: 4 }} />
                <Text style={typography.small}>Approved</Text>
              </View>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: "#FBBF24", marginRight: 4 }} />
                <Text style={typography.small}>Pending</Text>
              </View>
            </View>

            <Text style={[typography.label, { marginTop: 16, marginBottom: 6 }]}>Requests</Text>
            {holidays.length === 0 ? (
              <Text style={[typography.small, { color: colors.textMuted }]}>No requests yet.</Text>
            ) : (
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
              ))
            )}
          </>
        )}

        {tab === "shifts" && (
          <>
            <TouchableOpacity style={styles.addCta} onPress={() => setShiftModal(true)}>
              <Feather name="plus" size={16} color="#fff" />
              <Text style={styles.addCtaText}>Assign New Shift</Text>
            </TouchableOpacity>

            {/* Pending swap requests */}
            {swaps.filter((s) => s.status === "pending").length > 0 && (
              <>
                <Text style={[typography.label, { marginTop: 8 }]}>Swap Requests</Text>
                {swaps.filter((s) => s.status === "pending").map((sw) => (
                  <View key={sw.id} style={styles.card} testID={`swap-${sw.id}`}>
                    <View style={[styles.smBtn, { backgroundColor: "#FEF3C7", width: 36, height: 36, borderRadius: 18 }]}>
                      <Feather name="repeat" size={16} color="#92400E" />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontWeight: "700", color: colors.primary }}>
                        {sw.from_user_name} → {sw.to_user_name}
                      </Text>
                      {sw.reason ? <Text style={typography.small}>{sw.reason}</Text> : null}
                    </View>
                    <View style={{ flexDirection: "row", gap: 6 }}>
                      <TouchableOpacity
                        testID={`swap-approve-${sw.id}`}
                        style={[styles.smBtn, { backgroundColor: colors.success }]}
                        onPress={() => decideSwap(sw.id, "approved")}
                      >
                        <Feather name="check" size={14} color="#fff" />
                      </TouchableOpacity>
                      <TouchableOpacity
                        testID={`swap-reject-${sw.id}`}
                        style={[styles.smBtn, { backgroundColor: colors.alert }]}
                        onPress={() => decideSwap(sw.id, "rejected")}
                      >
                        <Feather name="x" size={14} color="#fff" />
                      </TouchableOpacity>
                    </View>
                  </View>
                ))}
              </>
            )}

            {/* Team availability snapshot */}
            {availability.filter((a) => !a.available).length > 0 && (
              <>
                <Text style={[typography.label, { marginTop: 8 }]}>Team Unavailability</Text>
                <View style={[styles.card, { flexDirection: "column", alignItems: "stretch" }]}>
                  {availability.filter((a) => !a.available).slice(0, 8).map((a, i) => (
                    <View key={i} style={{ flexDirection: "row", alignItems: "center", paddingVertical: 4 }}>
                      <Feather name="user-x" size={12} color={colors.alert} />
                      <Text style={[typography.small, { marginLeft: 6, flex: 1 }]}>
                        {a.user_name} · {a.date}
                        {a.note ? ` · ${a.note}` : ""}
                      </Text>
                    </View>
                  ))}
                </View>
              </>
            )}

            <Text style={[typography.label, { marginTop: 8 }]}>All Shifts</Text>
            {allShifts.map((s) => (
              <TouchableOpacity
                key={s.id}
                style={styles.card}
                testID={`admin-shift-${s.id}`}
                activeOpacity={0.7}
                onPress={() => {
                  setEditShift(s);
                  setETitle(s.title || "");
                  setEStart((s.start || "").slice(0, 16));
                  setEEnd((s.end || "").slice(0, 16));
                  setELoc(s.location || "");
                  setEUser(s.user_id || "");
                }}
              >
                <View style={{ flex: 1 }}>
                  <Text style={{ fontWeight: "700", color: colors.primary }}>
                    {s.title}
                    {s.recurring && s.recurring !== "none" ? ` · ${s.recurring}` : ""}
                  </Text>
                  <Text style={typography.small}>{s.user_name} · {s.start?.slice(0, 16)} → {s.end?.slice(11, 16)}</Text>
                  {s.customer_name ? (
                    <Text style={[typography.small, { color: colors.brand, marginTop: 2 }]}>
                      <Feather name="briefcase" size={10} color={colors.brand} /> {s.customer_name}
                      {s.site_name ? ` · ${s.site_name}` : ""}
                    </Text>
                  ) : null}
                </View>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <Feather name="edit-2" size={14} color={colors.primary} />
                  <TouchableOpacity onPress={async (e) => { e.stopPropagation && e.stopPropagation(); await api.delete(`/shifts/${s.id}`); await load(); }}>
                    <Feather name="trash-2" size={16} color={colors.alert} />
                  </TouchableOpacity>
                </View>
              </TouchableOpacity>
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

        {tab === "pdf-forms" && (
          <>
            <TouchableOpacity
              testID="open-pdf-upload"
              style={styles.addCta}
              onPress={() => setPdfModalOpen(true)}
            >
              <Feather name="upload" size={16} color="#fff" />
              <Text style={styles.addCtaText}>Upload PDF Template</Text>
            </TouchableOpacity>
            <Text style={[typography.small, { marginTop: 8, marginBottom: 4 }]}>
              Upload PDFs with AcroForm (fillable) fields. Staff can fill them on mobile and share the completed PDF.
            </Text>
            {pdfTemplates.length === 0 ? (
              <Text style={[typography.small, { marginTop: 12, color: colors.textMuted }]}>
                No PDF templates yet.
              </Text>
            ) : (
              pdfTemplates.map((t) => (
                <View key={t.id} style={styles.card} testID={`pdf-tpl-${t.id}`}>
                  <View style={[styles.smBtn, { backgroundColor: t.has_acroform ? "#FEE2E2" : colors.surface, width: 36, height: 36, borderRadius: 18 }]}>
                    <Feather name="file-text" size={16} color={t.has_acroform ? "#B91C1C" : colors.textMuted} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontWeight: "700", color: colors.primary }}>{t.title}</Text>
                    <Text style={typography.small}>
                      {t.has_acroform
                        ? `${t.field_count} fields · ${formatBytesAdmin(t.size_bytes || 0)}`
                        : "No AcroForm fields detected"}
                    </Text>
                  </View>
                  <TouchableOpacity
                    onPress={async () => {
                      Alert.alert("Delete?", `Delete ${t.title}?`, [
                        { text: "Cancel", style: "cancel" },
                        {
                          text: "Delete",
                          style: "destructive",
                          onPress: async () => {
                            await api.delete(`/pdf-forms/templates/${t.id}`);
                            await load();
                          },
                        },
                      ]);
                    }}
                  >
                    <Feather name="trash-2" size={14} color={colors.alert} />
                  </TouchableOpacity>
                </View>
              ))
            )}
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
                  <Text style={[typography.small, { marginTop: 2 }]}>
                    Holiday entitlement: {u.holiday_entitlement ?? 25} days
                  </Text>
                </View>
                <TouchableOpacity
                  testID={`edit-entitlement-${u.id}`}
                  style={[styles.smBtn, { backgroundColor: colors.brand }]}
                  onPress={() => {
                    setEntUser(u);
                    setEntValue(String(u.holiday_entitlement ?? 25));
                  }}
                >
                  <Feather name="calendar" size={14} color="#fff" />
                </TouchableOpacity>
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

        {tab === "offsite" && (
          <>
            <OffsiteMap
              entries={offsite}
              depots={depots}
              sites={customers.flatMap((c: any) =>
                (c.sites || [])
                  .filter((st: any) => st.lat != null && st.lng != null)
                  .map((st: any) => ({ ...st, customer_name: c.name }))
              )}
            />

            <View style={{ marginBottom: 8, gap: 6 }}>
              <Text style={typography.label}>Filter by depot</Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
                <TouchableOpacity
                  testID="off-depot-all"
                  style={[styles.typeChip, !offDepot && { backgroundColor: colors.primary }]}
                  onPress={() => setOffDepot("")}
                >
                  <Text style={{ color: !offDepot ? "#fff" : colors.primary, fontWeight: "600", fontSize: 12 }}>All</Text>
                </TouchableOpacity>
                {depots.map((d) => (
                  <TouchableOpacity
                    key={d.id}
                    testID={`off-depot-${d.id}`}
                    style={[styles.typeChip, offDepot === d.id && { backgroundColor: colors.primary }]}
                    onPress={() => setOffDepot(d.id)}
                  >
                    <Text style={{ color: offDepot === d.id ? "#fff" : colors.primary, fontWeight: "600", fontSize: 12 }}>
                      {d.name}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={[typography.label, { marginTop: 8 }]}>Filter by employee</Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
                <TouchableOpacity
                  testID="off-user-all"
                  style={[styles.typeChip, !offUser && { backgroundColor: colors.primary }]}
                  onPress={() => setOffUser("")}
                >
                  <Text style={{ color: !offUser ? "#fff" : colors.primary, fontWeight: "600", fontSize: 12 }}>All</Text>
                </TouchableOpacity>
                {users.map((u) => (
                  <TouchableOpacity
                    key={u.id}
                    testID={`off-user-${u.id}`}
                    style={[styles.typeChip, offUser === u.id && { backgroundColor: colors.primary }]}
                    onPress={() => setOffUser(u.id)}
                  >
                    <Text style={{ color: offUser === u.id ? "#fff" : colors.primary, fontWeight: "600", fontSize: 12 }}>
                      {u.name}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <View style={{ flexDirection: "row", gap: 8, marginTop: 8 }}>
                <TextInput
                  testID="off-from"
                  style={[styles.input, { flex: 1, marginTop: 0 }]}
                  placeholder="From (YYYY-MM-DD)"
                  value={offFrom}
                  onChangeText={setOffFrom}
                  placeholderTextColor={colors.textMuted}
                />
                <TextInput
                  testID="off-to"
                  style={[styles.input, { flex: 1, marginTop: 0 }]}
                  placeholder="To (YYYY-MM-DD)"
                  value={offTo}
                  onChangeText={setOffTo}
                  placeholderTextColor={colors.textMuted}
                />
              </View>
              <TouchableOpacity
                testID="off-apply"
                style={[styles.modalBtn, { backgroundColor: colors.primary, height: 40, marginTop: 4 }]}
                onPress={load}
              >
                <Text style={{ color: "#fff", fontWeight: "700" }}>Apply Filters</Text>
              </TouchableOpacity>
            </View>

            <Text style={[typography.label, { marginBottom: 8 }]}>{offsite.length} result{offsite.length === 1 ? "" : "s"}</Text>
            {offsite.length === 0 ? (
              <Text style={typography.body}>✓ No off-site clock-ins.</Text>
            ) : (
              offsite.map((e) => (
                <View key={e.id} style={styles.card} testID={`offsite-${e.id}`}>
                  <View style={[styles.smBtn, { backgroundColor: "#FEE2E2", width: 36, height: 36, borderRadius: 18 }]}>
                    <Feather name="map-pin" size={16} color={colors.alert} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontWeight: "700", color: colors.primary }}>{e.user_name}</Text>
                    <Text style={typography.small}>
                      {e.distance_m != null ? (e.distance_m > 1000 ? `${(e.distance_m / 1000).toFixed(1)}km` : `${Math.round(e.distance_m)}m`) : "—"} from {e.depot_name || "any depot"} · {new Date(e.clock_in).toLocaleString()}
                    </Text>
                    <Text style={[typography.small, { color: colors.textMuted }]}>
                      {e.lat?.toFixed?.(4)}, {e.lng?.toFixed?.(4)}
                    </Text>
                  </View>
                  {e.lat != null && e.lng != null && (
                    <TouchableOpacity
                      testID={`map-${e.id}`}
                      onPress={() => openInMaps(e.lat, e.lng)}
                      style={[styles.smBtn, { backgroundColor: colors.brand, width: 64, borderRadius: 14 }]}
                    >
                      <Feather name="map" size={14} color="#fff" />
                      <Text style={{ color: "#fff", fontSize: 11, fontWeight: "700", marginLeft: 4 }}>Map</Text>
                    </TouchableOpacity>
                  )}
                </View>
              ))
            )}
          </>
        )}

        {tab === "customers" && (
          <>
            <TouchableOpacity testID="open-new-customer" style={styles.addCta} onPress={() => setNewCustomerModal(true)}>
              <Feather name="user-plus" size={16} color="#fff" />
              <Text style={styles.addCtaText}>Add Customer</Text>
            </TouchableOpacity>
            <Text style={[typography.small, { marginTop: 8, marginBottom: 4 }]}>
              Crew tap a customer to view contacts, locations, and notes. Assign shifts to a customer site to auto-notify on arrival.
            </Text>
            {customers.map((c) => (
              <TouchableOpacity
                key={c.id}
                testID={`customer-${c.id}`}
                style={styles.card}
                onPress={() => setActiveCustomerId(c.id)}
              >
                <View style={[styles.smBtn, { backgroundColor: colors.brandSoft, width: 36, height: 36, borderRadius: 18 }]}>
                  <Feather name="briefcase" size={16} color={colors.brand} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontWeight: "700", color: colors.primary }}>{c.name}</Text>
                  <Text style={typography.small}>
                    {c.company || "—"} · {(c.contacts || []).length} contacts · {(c.sites || []).length} sites
                  </Text>
                </View>
                <Feather name="chevron-right" size={16} color={colors.textMuted} />
              </TouchableOpacity>
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
              {users.filter((u) => u.role === "staff").map((u) => {
                const dateOnly = (sStart || "").slice(0, 10);
                const unavailable = !!availability.find(
                  (a) => a.user_id === u.id && a.date === dateOnly && a.available === false
                );
                return (
                  <TouchableOpacity
                    key={u.id}
                    style={[
                      styles.userRow,
                      sUser === u.id && styles.userRowActive,
                      unavailable && { opacity: 0.6, backgroundColor: "#FEF3C7" },
                    ]}
                    onPress={() => setSUser(u.id)}
                    testID={`shift-pick-user-${u.id}`}
                  >
                    <Text style={{ flex: 1 }}>{u.name}</Text>
                    {unavailable ? (
                      <View style={{ flexDirection: "row", alignItems: "center" }}>
                        <Feather name="alert-triangle" size={12} color="#92400E" />
                        <Text style={{ marginLeft: 4, color: "#92400E", fontSize: 11, fontWeight: "700" }}>
                          Unavailable
                        </Text>
                      </View>
                    ) : null}
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
            <TextInput style={styles.input} placeholder="Title" value={sTitle} onChangeText={setSTitle} placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="Start (YYYY-MM-DDTHH:MM)" value={sStart} onChangeText={setSStart} placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="End (YYYY-MM-DDTHH:MM)" value={sEnd} onChangeText={setSEnd} placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="Location (free-text)" value={sLoc} onChangeText={setSLoc} placeholderTextColor={colors.textMuted} />

            {customers.length > 0 && (
              <>
                <Text style={[typography.label, { marginTop: 8 }]}>Customer (optional)</Text>
                <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                  <TouchableOpacity
                    testID="shift-cust-none"
                    style={[styles.typeChip, !sCustomerId && { backgroundColor: colors.primary }]}
                    onPress={() => { setSCustomerId(""); setSSiteId(""); }}
                  >
                    <Text style={{ color: !sCustomerId ? "#fff" : colors.primary, fontWeight: "600", fontSize: 12 }}>None</Text>
                  </TouchableOpacity>
                  {customers.map((c) => (
                    <TouchableOpacity
                      key={c.id}
                      testID={`shift-cust-${c.id}`}
                      style={[styles.typeChip, sCustomerId === c.id && { backgroundColor: colors.primary }]}
                      onPress={() => { setSCustomerId(c.id); setSSiteId(""); }}
                    >
                      <Text style={{ color: sCustomerId === c.id ? "#fff" : colors.primary, fontWeight: "600", fontSize: 12 }}>
                        {c.name}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
                {sCustomerId && (() => {
                  const cust = customers.find((c) => c.id === sCustomerId);
                  const sites = cust?.sites || [];
                  if (sites.length === 0)
                    return <Text style={[typography.small, { marginTop: 6, color: colors.textMuted }]}>No sites for this customer.</Text>;
                  return (
                    <>
                      <Text style={[typography.label, { marginTop: 8 }]}>Site</Text>
                      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                        {sites.map((st: any) => (
                          <TouchableOpacity
                            key={st.id}
                            testID={`shift-site-${st.id}`}
                            style={[styles.typeChip, sSiteId === st.id && { backgroundColor: colors.brand }]}
                            onPress={() => setSSiteId(st.id)}
                          >
                            <Text style={{ color: sSiteId === st.id ? "#fff" : colors.primary, fontWeight: "600", fontSize: 12 }}>
                              {st.name}
                            </Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                    </>
                  );
                })()}
              </>
            )}
            <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
              <Text style={[typography.label]}>Repeat</Text>
            </View>
            <View style={{ flexDirection: "row", gap: 6, marginTop: 4 }}>
              {(["none", "daily", "weekly"] as const).map((r) => (
                <TouchableOpacity
                  key={r}
                  testID={`shift-repeat-${r}`}
                  style={[styles.typeChip, sRecurring === r && { backgroundColor: colors.primary }]}
                  onPress={() => setSRecurring(r)}
                >
                  <Text style={{ color: sRecurring === r ? "#fff" : colors.primary, fontWeight: "600", fontSize: 12 }}>
                    {r}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
            {sRecurring !== "none" && (
              <TextInput
                testID="shift-repeat-count"
                style={styles.input}
                placeholder="Number of occurrences (e.g. 4)"
                value={sRepeat}
                onChangeText={setSRepeat}
                keyboardType="numeric"
                placeholderTextColor={colors.textMuted}
              />
            )}
            <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
              <TouchableOpacity style={[styles.modalBtn, { backgroundColor: colors.surface }]} onPress={() => setShiftModal(false)}>
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="shift-assign-submit" style={[styles.modalBtn, { backgroundColor: colors.primary }]} onPress={createShift}>
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
      <CustomerModal customerId={activeCustomerId} onClose={() => { setActiveCustomerId(null); load(); }} />

      {/* New Customer Modal */}
      <Modal visible={newCustomerModal} animationType="slide" transparent onRequestClose={() => setNewCustomerModal(false)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <Text style={typography.h3}>New Customer</Text>
            <TextInput testID="cust-name" style={styles.input} placeholder="Name (e.g. Aer Lingus)" value={ncName} onChangeText={setNcName} placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="Company" value={ncCompany} onChangeText={setNcCompany} placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="Email" value={ncEmail} onChangeText={setNcEmail} autoCapitalize="none" placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="Phone" value={ncPhone} onChangeText={setNcPhone} placeholderTextColor={colors.textMuted} />
            <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
              <TouchableOpacity style={[styles.modalBtn, { backgroundColor: colors.surface }]} onPress={() => setNewCustomerModal(false)}>
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="cust-submit" style={[styles.modalBtn, { backgroundColor: colors.primary }]} onPress={async () => {
                if (!ncName) return Alert.alert("Name required");
                try {
                  const { data } = await api.post("/customers", { name: ncName, company: ncCompany, email: ncEmail, phone: ncPhone });
                  setNewCustomerModal(false);
                  setNcName(""); setNcCompany(""); setNcEmail(""); setNcPhone("");
                  await load();
                  setActiveCustomerId(data.id);
                } catch (e: any) {
                  Alert.alert("Error", e.response?.data?.detail || "Failed");
                }
              }}>
                <Text style={{ color: "#fff", fontWeight: "700" }}>Create & Open</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

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

      {/* Entitlement Editor */}
      <Modal visible={!!entUser} animationType="fade" transparent onRequestClose={() => setEntUser(null)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <Text style={typography.h3}>Holiday Entitlement</Text>
            {entUser ? (
              <Text style={[typography.small, { marginTop: 4 }]}>
                {entUser.name} · {entUser.email}
              </Text>
            ) : null}
            <TextInput
              testID="entitlement-input"
              style={styles.input}
              value={entValue}
              onChangeText={setEntValue}
              keyboardType="numeric"
              placeholder="Days (0-365)"
              placeholderTextColor={colors.textMuted}
            />
            <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
              <TouchableOpacity style={[styles.modalBtn, { backgroundColor: colors.surface }]} onPress={() => setEntUser(null)}>
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="entitlement-save"
                style={[styles.modalBtn, { backgroundColor: colors.primary }]}
                onPress={async () => {
                  const v = Math.max(0, Math.min(365, parseInt(entValue || "0", 10) || 0));
                  try {
                    await api.patch(`/users/${entUser.id}/entitlement`, null, { params: { value: v } });
                    setEntUser(null);
                    await load();
                  } catch (e: any) {
                    Alert.alert("Error", e.response?.data?.detail || "Failed");
                  }
                }}
              >
                <Text style={{ color: "#fff", fontWeight: "700" }}>Save</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Edit Shift Modal (tap-to-edit) */}
      <Modal visible={!!editShift} animationType="slide" transparent onRequestClose={() => setEditShift(null)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <Text style={typography.h3}>Edit Shift</Text>
            <ScrollView style={{ maxHeight: 140, marginTop: 8 }}>
              {users.filter((u) => u.role === "staff").map((u) => {
                const dateOnly = (eStart || "").slice(0, 10);
                const unavailable = !!availability.find(
                  (a) => a.user_id === u.id && a.date === dateOnly && a.available === false
                );
                return (
                  <TouchableOpacity
                    key={u.id}
                    style={[
                      styles.userRow,
                      eUser === u.id && styles.userRowActive,
                      unavailable && { opacity: 0.6, backgroundColor: "#FEF3C7" },
                    ]}
                    onPress={() => setEUser(u.id)}
                  >
                    <Text style={{ flex: 1 }}>{u.name}</Text>
                    {unavailable ? (
                      <View style={{ flexDirection: "row", alignItems: "center" }}>
                        <Feather name="alert-triangle" size={12} color="#92400E" />
                        <Text style={{ marginLeft: 4, color: "#92400E", fontSize: 11, fontWeight: "700" }}>
                          Unavailable
                        </Text>
                      </View>
                    ) : null}
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
            <TextInput style={styles.input} placeholder="Title" value={eTitle} onChangeText={setETitle} placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="Start (YYYY-MM-DDTHH:MM)" value={eStart} onChangeText={setEStart} placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="End (YYYY-MM-DDTHH:MM)" value={eEnd} onChangeText={setEEnd} placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="Location" value={eLoc} onChangeText={setELoc} placeholderTextColor={colors.textMuted} />
            <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
              <TouchableOpacity style={[styles.modalBtn, { backgroundColor: colors.surface }]} onPress={() => setEditShift(null)}>
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="edit-shift-save"
                style={[styles.modalBtn, { backgroundColor: colors.primary }]}
                onPress={async () => {
                  if (!editShift || !eUser || !eTitle || !eStart || !eEnd) {
                    return Alert.alert("Missing info");
                  }
                  try {
                    await api.patch(`/shifts/${editShift.id}`, {
                      user_id: eUser,
                      title: eTitle,
                      start: eStart,
                      end: eEnd,
                      location: eLoc,
                    });
                    setEditShift(null);
                    await load();
                  } catch (e: any) {
                    Alert.alert("Error", e.response?.data?.detail || "Failed");
                  }
                }}
              >
                <Text style={{ color: "#fff", fontWeight: "700" }}>Save</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* PDF Upload Modal */}
      <Modal visible={pdfModalOpen} animationType="slide" transparent onRequestClose={() => setPdfModalOpen(false)}>        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <Text style={typography.h3}>Upload PDF Form</Text>
            <Text style={[typography.small, { marginTop: 4 }]}>
              We'll auto-detect AcroForm (fillable) fields so staff can fill on mobile.
            </Text>
            <TextInput
              testID="pdf-title-input"
              style={styles.input}
              placeholder="Title (e.g. Vehicle Inspection)"
              value={pdfTitle}
              onChangeText={setPdfTitle}
              placeholderTextColor={colors.textMuted}
            />
            <TextInput
              style={[styles.input, { height: 72, paddingTop: 10 }]}
              placeholder="Description (optional)"
              value={pdfDesc}
              onChangeText={setPdfDesc}
              multiline
              placeholderTextColor={colors.textMuted}
            />
            <View style={{ marginTop: spacing.sm }}>
              <WebDropZone
                onFile={onWebDrop}
                style={{ minHeight: 92, alignItems: "center", justifyContent: "center" } as any}
              >
                <TouchableOpacity
                  testID="pick-pdf-btn"
                  onPress={pickPdf}
                  style={{ alignItems: "center", justifyContent: "center", padding: 8 }}
                >
                  <Feather name={pdfPicked ? "check-circle" : "upload-cloud"} size={22} color={pdfPicked ? colors.success : colors.primary} />
                  <Text style={{ marginTop: 6, color: colors.primary, fontWeight: "700" }} numberOfLines={1}>
                    {pdfPicked ? pdfPicked.name : Platform.OS === "web" ? "Drag PDF here, or tap to pick" : "Tap to pick PDF file"}
                  </Text>
                  {!pdfPicked && Platform.OS === "web" ? (
                    <Text style={[typography.small, { marginTop: 2, color: colors.textMuted }]}>Drop a .pdf or click anywhere</Text>
                  ) : null}
                </TouchableOpacity>
              </WebDropZone>
            </View>
            <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
              <TouchableOpacity
                style={[styles.modalBtn, { backgroundColor: colors.surface }]}
                onPress={() => {
                  setPdfModalOpen(false);
                  setPdfPicked(null);
                  setPdfTitle("");
                  setPdfDesc("");
                }}
              >
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="pdf-upload-submit"
                style={[styles.modalBtn, { backgroundColor: colors.primary, opacity: pdfUploading ? 0.6 : 1 }]}
                onPress={uploadPdfTemplate}
                disabled={pdfUploading}
              >
                <Text style={{ color: "#fff", fontWeight: "700" }}>
                  {pdfUploading ? "Uploading…" : "Upload"}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function formatBytesAdmin(n: number) {
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

async function readAssetAsBase64(file: any, FileSystem: any): Promise<string> {
  // 1) Already provided
  if (file?.base64) return file.base64;
  // 2) Web returns a File object on `.file`
  if (Platform.OS === "web") {
    if (file?.file) {
      try {
        const ab = await file.file.arrayBuffer();
        const bytes = new Uint8Array(ab);
        let binary = "";
        for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
        return btoa(binary);
      } catch {}
    }
    // 3) data URL fallback
    if (typeof file?.uri === "string" && file.uri.startsWith("data:")) {
      const idx = file.uri.indexOf(",");
      if (idx >= 0) return file.uri.slice(idx + 1);
    }
    // 4) blob URL — fetch it
    if (typeof file?.uri === "string" && file.uri.startsWith("blob:")) {
      try {
        const r = await fetch(file.uri);
        const blob = await r.blob();
        const ab = await blob.arrayBuffer();
        const bytes = new Uint8Array(ab);
        let binary = "";
        for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
        return btoa(binary);
      } catch {}
    }
  }
  // 5) Native: use FileSystem
  try {
    return await FileSystem.readAsStringAsync(file.uri, {
      encoding: FileSystem.EncodingType.Base64,
    });
  } catch {
    return "";
  }
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
