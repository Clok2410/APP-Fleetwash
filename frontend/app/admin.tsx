import React, { useCallback, useState, useEffect } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  Modal,
  TextInput,
  useWindowDimensions,
} from "react-native";
import { useFocusEffect, useRouter, Redirect, useLocalSearchParams } from "expo-router";
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
import HRProfileModal from "../src/components/HRProfileModal";
import WebDropZone from "../src/components/WebDropZone";
import { readAssetAsBase64 } from "../src/utils/fileToBase64";
import { Calendar } from "react-native-calendars";

export default function AdminScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ openRoster?: string; tab?: string }>();
  const { user } = useAuth();
  const [tab, setTab] = useState<"holidays" | "shifts" | "hours" | "forms" | "pdf-forms" | "users" | "depots" | "offsite" | "customers" | "hr">("holidays");
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
  const [pdfAssignedIds, setPdfAssignedIds] = useState<string[]>([]); // empty = assign to ALL
  const [assignModalFor, setAssignModalFor] = useState<any>(null); // PDF template being assigned
  const [editEntry, setEditEntry] = useState<any>(null); // clock entry being edited by admin
  const [editIn, setEditIn] = useState("");
  const [editOut, setEditOut] = useState("");
  // Drag-and-drop reassignment (web/desktop only)
  const [dragShiftId, setDragShiftId] = useState<string | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);
  // Roster PDF import
  const [rosterOpen, setRosterOpen] = useState(false);
  const [rosterFile, setRosterFile] = useState<{ name: string; base64: string } | null>(null);
  const [rosterParsing, setRosterParsing] = useState(false);
  const [rosterPublishing, setRosterPublishing] = useState(false);
  const [rosterRows, setRosterRows] = useState<any[]>([]); // [{name, mon, tue, ..., user_id?}]
  const [rosterWeekStart, setRosterWeekStart] = useState(""); // YYYY-MM-DD
  const [rosterStartTime, setRosterStartTime] = useState("06:30");
  const [rosterNotify, setRosterNotify] = useState(true);
  const [rosterTemplates, setRosterTemplates] = useState<any[]>([]);

  // Deep-link: ?openRoster=1 (from Schedule tab AI banner) → jump to Shifts + open roster modal
  useEffect(() => {
    if (params?.openRoster === "1") {
      setTab("shifts");
      setRosterOpen(true);
    } else if (typeof params?.tab === "string") {
      const t = params.tab as any;
      if (["holidays","shifts","hours","forms","pdf-forms","users","depots","offsite","customers","hr"].includes(t)) {
        setTab(t);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params?.openRoster, params?.tab]);
  // A1: Holiday detail drawer
  const [holidayDetail, setHolidayDetail] = useState<any>(null);
  const [hdStart, setHdStart] = useState("");
  const [hdEnd, setHdEnd] = useState("");
  const [hdReason, setHdReason] = useState("");
  const [hdType, setHdType] = useState<"annual" | "sick" | "unpaid">("annual");
  // A2: Forms tab — Submissions Inbox
  const [formsView, setFormsView] = useState<"inbox" | "templates">("inbox");
  const [inbox, setInbox] = useState<any[]>([]);
  const [inboxLoading, setInboxLoading] = useState(false);
  const [fxTemplate, setFxTemplate] = useState<string>(""); // template_id filter
  const [fxUser, setFxUser] = useState<string>(""); // user_id filter
  const [fxFrom, setFxFrom] = useState<string>("");
  const [fxTo, setFxTo] = useState<string>("");
  const [fxReviewed, setFxReviewed] = useState<"all" | "true" | "false">("all");
  const [fxKind, setFxKind] = useState<"all" | "form" | "pdf">("all");
  const [inboxDownloading, setInboxDownloading] = useState<string | null>(null);
  const [depots, setDepots] = useState<any[]>([]);
  const [allDepots, setAllDepots] = useState<any[]>([]); // unified depots + customer locations
  const [offsite, setOffsite] = useState<any[]>([]);
  const [customers, setCustomers] = useState<any[]>([]);
  const [activeCustomerId, setActiveCustomerId] = useState<string | null>(null);
  // A3: HR profile
  const [hrStaff, setHrStaff] = useState<any[]>([]);
  // Hours Sheets state
  const [hoursWeek, setHoursWeek] = useState<string>(""); // YYYY-MM-DD Monday; empty=current
  const [hoursData, setHoursData] = useState<any>(null);
  const [hoursLoading, setHoursLoading] = useState(false);
  const [hoursEditEntry, setHoursEditEntry] = useState<any | null>(null);
  const [hoursDetailUserId, setHoursDetailUserId] = useState<string | null>(null);
  const [hoursDetailEntries, setHoursDetailEntries] = useState<any[]>([]);
  const [hrActiveUserId, setHrActiveUserId] = useState<string | null>(null);
  const [newCustomerModal, setNewCustomerModal] = useState(false);
  const [ncName, setNcName] = useState("");
  const [ncCompany, setNcCompany] = useState("");
  const [ncEmail, setNcEmail] = useState("");
  const [ncPhone, setNcPhone] = useState("");
  const [ncAddress, setNcAddress] = useState("");
  const [ncEircode, setNcEircode] = useState("");
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
  // Admin-edit-user (Phase 2): full profile editor
  const [editUser, setEditUser] = useState<any>(null);
  const [euName, setEuName] = useState("");
  const [euEmail, setEuEmail] = useState("");
  const [euPhone, setEuPhone] = useState("");
  const [euDob, setEuDob] = useState("");
  const [euPps, setEuPps] = useState("");
  const [euStart, setEuStart] = useState("");
  const [euType, setEuType] = useState<"full_time" | "part_time">("full_time");
  const [euEnt, setEuEnt] = useState("25");
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
      const [h, u, s, t, d, o, cust, pft, sw, av, dAll] = await Promise.all([
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
        api.get("/depots/all").catch(() => ({ data: [] })),
      ]);
      setHolidays(h.data);
      setUsers(u.data);
      setAllShifts(s.data);
      setAllTemplates(t.data);
      setDepots(d.data);
      setAllDepots(dAll.data || []);
      setOffsite(o.data || []);
      setCustomers(cust.data || []);
      setPdfTemplates(pft.data || []);
      setSwaps(sw.data || []);
      setAvailability(av.data || []);
    } catch {}
  }, [offDepot, offUser, offFrom, offTo]);

  const openInMaps = (lat: number, lng: number, label?: string) => {
    const q = label ? encodeURIComponent(label) : "";
    const url = Platform.select({
      ios: `https://maps.apple.com/?ll=${lat},${lng}${q ? `&q=${q}` : ""}`,
      default: `https://www.google.com/maps?q=${lat},${lng}${q ? `(${q})` : ""}`,
    })!;
    if (Platform.OS === "web" && typeof window !== "undefined") {
      const w = window.open(url, "_blank", "noopener,noreferrer");
      if (!w) Alert.alert("Popup blocked", "Allow popups for this site.");
      return;
    }
    Linking.openURL(url).catch(() => Alert.alert("Couldn't open Maps"));
  };

  // Generic open: address or eircode → Maps search (used for customer sites with no lat/lng)
  const openMapsAddress = (q?: string) => {
    if (!q || !q.trim()) {
      Alert.alert("No address", "This depot has no address. Add one in the customer record first.");
      return;
    }
    const enc = encodeURIComponent(q.trim());
    const url = Platform.select({
      ios: `https://maps.apple.com/?q=${enc}`,
      default: `https://www.google.com/maps/search/?api=1&query=${enc}`,
    })!;
    if (Platform.OS === "web" && typeof window !== "undefined") {
      const w = window.open(url, "_blank", "noopener,noreferrer");
      if (!w) Alert.alert("Popup blocked", "Allow popups for this site.");
      return;
    }
    Linking.openURL(url).catch(() => Alert.alert("Couldn't open Maps"));
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

  // A2: Auto-load inbox when entering Forms→Inbox view or when filters change
  useEffect(() => {
    if (tab === "forms" && formsView === "inbox") {
      loadInbox();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, formsView, fxTemplate, fxUser, fxFrom, fxTo, fxReviewed, fxKind]);

  // A3: Load HR staff directory when entering HR tab
  const loadHrStaff = useCallback(async () => {
    try {
      const { data } = await api.get("/hr/staff");
      setHrStaff(Array.isArray(data) ? data : []);
    } catch (e) {
      setHrStaff([]);
    }
  }, []);
  useEffect(() => {
    if (tab === "hr") loadHrStaff();
  }, [tab, loadHrStaff]);

  // Hours Sheets loader
  const loadHours = useCallback(async (weekStart?: string) => {
    setHoursLoading(true);
    try {
      const ws = (weekStart ?? hoursWeek).trim();
      const { data } = await api.get("/clock/hours-sheet", { params: ws ? { week_start: ws } : {} });
      setHoursData(data);
      if (!weekStart && !hoursWeek) setHoursWeek(data.week_start);
    } catch (e) {
      setHoursData(null);
    } finally {
      setHoursLoading(false);
    }
  }, [hoursWeek]);
  useEffect(() => {
    if (tab === "hours") loadHours();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const loadHoursDetail = async (userId: string) => {
    setHoursDetailUserId(userId);
    try {
      const { data } = await api.get("/clock/history", { params: { user_id: userId } });
      // Filter to current visible week
      const ws = hoursData?.week_start;
      const we = hoursData?.week_end;
      const inRange = (data || []).filter((e: any) => {
        const d = (e.clock_in || "").slice(0, 10);
        return d >= ws && d <= we;
      });
      setHoursDetailEntries(inRange);
    } catch {
      setHoursDetailEntries([]);
    }
  };

  const shiftHoursWeek = (deltaDays: number) => {
    const cur = hoursWeek || hoursData?.week_start || new Date().toISOString().slice(0, 10);
    const d = new Date(cur + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + deltaDays);
    const next = d.toISOString().slice(0, 10);
    setHoursWeek(next);
    loadHours(next);
  };

  const saveHoursEntry = async () => {
    if (!hoursEditEntry) return;
    try {
      await api.patch(`/clock/entries/${hoursEditEntry.id}`, {
        clock_in: hoursEditEntry.clock_in_iso,
        clock_out: hoursEditEntry.clock_out_iso,
        note: hoursEditEntry.note,
      });
      setHoursEditEntry(null);
      if (hoursDetailUserId) await loadHoursDetail(hoursDetailUserId);
      await loadHours();
    } catch (e: any) {
      Alert.alert("Save failed", e.response?.data?.detail || "Try again");
    }
  };

  const deleteHoursEntry = async (id: string) => {
    if (!confirm_("Delete this clock entry permanently?")) return;
    try {
      await api.delete(`/clock/entries/${id}`);
      if (hoursDetailUserId) await loadHoursDetail(hoursDetailUserId);
      await loadHours();
    } catch (e: any) {
      Alert.alert("Delete failed", e.response?.data?.detail || "Try again");
    }
  };

  const confirm_ = (msg: string) => {
    if (Platform.OS === "web") return typeof window !== "undefined" ? window.confirm(msg) : true;
    // On native we can't synchronously confirm — assume yes (user already tapped)
    return true;
  };

  const exportHoursCsv = async () => {
    try {
      const token = (await import("@react-native-async-storage/async-storage")).default;
      const t = await token.getItem("access_token");
      const baseUrl = (process.env.EXPO_PUBLIC_BACKEND_URL || "").replace(/\/$/, "");
      const ws = hoursData?.week_start;
      const url = `${baseUrl}/api/clock/hours-sheet/export${ws ? `?week_start=${ws}` : ""}`;
      if (Platform.OS === "web") {
        const res = await fetch(url, { headers: { Authorization: `Bearer ${t}` } });
        const blob = await res.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `hours-sheet-${ws}.csv`;
        document.body.appendChild(a); a.click(); a.remove();
      } else {
        Alert.alert("Export", "CSV export is available on desktop/web.");
      }
    } catch (e: any) {
      Alert.alert("Export failed", String(e?.message || e));
    }
  };

  const decideHoliday = async (id: string, decision: string) => {
    await api.post(`/holidays/requests/${id}/decision`, null, { params: { decision } });
    await load();
  };

  const openHolidayDetail = (h: any) => {
    setHolidayDetail(h);
    setHdStart(h.start_date || "");
    setHdEnd(h.end_date || "");
    setHdReason(h.reason || "");
    setHdType((h.type as any) || "annual");
  };

  const saveHolidayEdit = async () => {
    if (!holidayDetail) return;
    if (hdStart && !/^\d{4}-\d{2}-\d{2}$/.test(hdStart)) return Alert.alert("Invalid start", "YYYY-MM-DD");
    if (hdEnd && !/^\d{4}-\d{2}-\d{2}$/.test(hdEnd)) return Alert.alert("Invalid end", "YYYY-MM-DD");
    try {
      await api.patch(`/holidays/requests/${holidayDetail.id}`, {
        start_date: hdStart,
        end_date: hdEnd,
        reason: hdReason,
        type: hdType,
      });
      setHolidayDetail(null);
      await load();
      Alert.alert("Saved", "Holiday request updated.");
    } catch (e: any) {
      Alert.alert("Failed", e.response?.data?.detail || "Try again");
    }
  };

  const decideInDetail = async (decision: "approved" | "rejected") => {
    if (!holidayDetail) return;
    await decideHoliday(holidayDetail.id, decision);
    setHolidayDetail(null);
  };

  const cancelInDetail = () => {
    if (!holidayDetail) return;
    cancelHoliday(holidayDetail);
    setHolidayDetail(null);
  };

  const cancelHoliday = (h: any) => {
    Alert.alert(
      "Cancel holiday?",
      `Cancel ${h.user_name}'s ${h.start_date} → ${h.end_date}? Days will be refunded.`,
      [
        { text: "Keep", style: "cancel" },
        {
          text: "Cancel it",
          style: "destructive",
          onPress: async () => {
            try {
              await api.post(`/holidays/requests/${h.id}/cancel`);
              await load();
            } catch (e: any) {
              Alert.alert("Failed", e.response?.data?.detail || "Try again");
            }
          },
        },
      ]
    );
  };

  // A2: Submissions Inbox
  const loadInbox = useCallback(async () => {
    setInboxLoading(true);
    try {
      const params: any = {};
      if (fxTemplate) params.template_id = fxTemplate;
      if (fxUser) params.user_id = fxUser;
      if (fxFrom) params.from_date = fxFrom;
      if (fxTo) params.to_date = fxTo;
      if (fxReviewed !== "all") params.reviewed = fxReviewed;
      if (fxKind !== "all") params.kind = fxKind;
      const { data } = await api.get("/admin/submissions-inbox", { params });
      setInbox(Array.isArray(data) ? data : []);
    } catch (e: any) {
      // Silent fail; admins will see empty list
      setInbox([]);
    } finally {
      setInboxLoading(false);
    }
  }, [fxTemplate, fxUser, fxFrom, fxTo, fxReviewed, fxKind]);

  const toggleReviewed = async (row: any) => {
    const nextReviewed = !row.reviewed;
    const endpoint =
      row.kind === "pdf"
        ? `/pdf-forms/submissions/${row.id}/review`
        : `/forms/submissions/${row.id}/review`;
    try {
      // Optimistic update
      setInbox((prev) => prev.map((r) => (r.id === row.id ? { ...r, reviewed: nextReviewed } : r)));
      await api.patch(endpoint, { reviewed: nextReviewed });
      await loadInbox();
    } catch (e: any) {
      // Revert
      setInbox((prev) => prev.map((r) => (r.id === row.id ? { ...r, reviewed: !nextReviewed } : r)));
      Alert.alert("Failed", e.response?.data?.detail || "Could not update reviewed status");
    }
  };

  const downloadSubmission = async (row: any) => {
    setInboxDownloading(row.id);
    try {
      if (row.kind === "pdf") {
        // Fetch full doc to get filled_pdf_base64
        const { data } = await api.get(`/pdf-forms/submissions/${row.id}`);
        const b64: string | undefined = data?.filled_pdf_base64;
        if (!b64) {
          Alert.alert("No PDF", "This submission has no filled PDF yet.");
          return;
        }
        const filename = `${(row.template_title || "submission").replace(/[^a-z0-9_-]+/gi, "_")}_${(row.user_name || "user").replace(/[^a-z0-9]+/gi, "_")}.pdf`;
        if (Platform.OS === "web") {
          const byteChars = atob(b64);
          const byteNums = new Array(byteChars.length);
          for (let i = 0; i < byteChars.length; i++) byteNums[i] = byteChars.charCodeAt(i);
          const blob = new Blob([new Uint8Array(byteNums)], { type: "application/pdf" });
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
          const path = `${FileSystem.cacheDirectory}${filename}`;
          await FileSystem.writeAsStringAsync(path, b64, { encoding: FileSystem.EncodingType.Base64 });
          if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(path);
        }
      } else {
        // Regular form — backend renders PDF via /forms/submissions/{sid}/pdf
        const filename = `${(row.template_title || "submission").replace(/[^a-z0-9_-]+/gi, "_")}_${(row.user_name || "user").replace(/[^a-z0-9]+/gi, "_")}.pdf`;
        if (Platform.OS === "web") {
          // Use auth header in fetch since StreamingResponse needs Bearer
          const token = (await import("@react-native-async-storage/async-storage")).default;
          const t = await token.getItem("access_token");
          const url = `/api/forms/submissions/${row.id}/pdf`;
          const resp = await fetch(url, { headers: { Authorization: `Bearer ${t}` } });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const blob = await resp.blob();
          const objUrl = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = objUrl;
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(objUrl), 1000);
        } else {
          // Native: download to cache then share
          const FileSystem = await import("expo-file-system");
          const Sharing = await import("expo-sharing");
          const AsyncStorage = (await import("@react-native-async-storage/async-storage")).default;
          const t = await AsyncStorage.getItem("access_token");
          const baseURL = (api.defaults?.baseURL || "").replace(/\/$/, "");
          const target = `${FileSystem.cacheDirectory}${filename}`;
          const result = await FileSystem.downloadAsync(
            `${baseURL}/forms/submissions/${row.id}/pdf`,
            target,
            { headers: { Authorization: `Bearer ${t}` } }
          );
          if (result.status === 200 && (await Sharing.isAvailableAsync())) {
            await Sharing.shareAsync(result.uri);
          }
        }
      }
    } catch (e: any) {
      Alert.alert("Download failed", String(e?.message || e));
    } finally {
      setInboxDownloading(null);
    }
  };

  const inboxTemplateOptions = React.useMemo(() => {
    const map = new Map<string, { id: string; title: string; kind: "form" | "pdf" }>();
    inbox.forEach((r) => {
      if (r.template_id && !map.has(r.template_id)) {
        map.set(r.template_id, { id: r.template_id, title: r.template_title || "Untitled", kind: r.kind });
      }
    });
    // Also include all known templates so filtering can show ones without submissions yet
    (allTemplates || []).forEach((t: any) => {
      if (!map.has(t.id)) map.set(t.id, { id: t.id, title: t.title, kind: "form" });
    });
    (pdfTemplates || []).forEach((t: any) => {
      if (!map.has(t.id)) map.set(t.id, { id: t.id, title: t.title, kind: "pdf" });
    });
    return Array.from(map.values()).sort((a, b) => a.title.localeCompare(b.title));
  }, [inbox, allTemplates, pdfTemplates]);

  const inboxUnreviewedCount = React.useMemo(
    () => inbox.filter((r) => !r.reviewed).length,
    [inbox]
  );

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
        assigned_user_ids: pdfAssignedIds,
      });
      setPdfModalOpen(false);
      setPdfPicked(null);
      setPdfTitle("");
      setPdfDesc("");
      setPdfAssignedIds([]);
      await load();
      const assignedMsg = pdfAssignedIds.length
        ? ` Assigned to ${pdfAssignedIds.length} staff.`
        : " Visible to all staff.";
      if (data.has_acroform) {
        Alert.alert("Uploaded", `Detected ${data.field_count} fillable fields.${assignedMsg}`);
      } else {
        Alert.alert("Uploaded", `No AcroForm fields were detected.${assignedMsg}`);
      }
    } catch (e: any) {
      Alert.alert("Upload failed", e.response?.data?.detail || "Try again");
    } finally {
      setPdfUploading(false);
    }
  };

  const saveAssignment = async () => {
    if (!assignModalFor) return;
    try {
      await api.patch(`/pdf-forms/templates/${assignModalFor.id}/assign`, {
        assigned_user_ids: assignModalFor.assigned_user_ids || [],
      });
      setAssignModalFor(null);
      await load();
      Alert.alert("Saved", "Assignment updated.");
    } catch (e: any) {
      Alert.alert("Failed", e.response?.data?.detail || "Try again");
    }
  };

  const toggleAssign = (userId: string) => {
    if (!assignModalFor) return;
    const cur = new Set<string>(assignModalFor.assigned_user_ids || []);
    if (cur.has(userId)) cur.delete(userId);
    else cur.add(userId);
    setAssignModalFor({ ...assignModalFor, assigned_user_ids: Array.from(cur) });
  };

  const openEditEntry = (entry: any) => {
    setEditEntry(entry);
    // Convert ISO timestamps to local "YYYY-MM-DDTHH:MM" for editing
    const toLocal = (iso: string | null | undefined) => {
      if (!iso) return "";
      const d = new Date(iso);
      const pad = (n: number) => String(n).padStart(2, "0");
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    };
    setEditIn(toLocal(entry.clock_in));
    setEditOut(toLocal(entry.clock_out));
  };

  const saveEditEntry = async () => {
    if (!editEntry) return;
    try {
      const toIso = (local: string) =>
        local ? new Date(local).toISOString() : "";
      await api.patch(`/clock/entries/${editEntry.id}`, {
        clock_in: editIn ? toIso(editIn) : undefined,
        clock_out: editOut === "" ? "" : toIso(editOut),
      });
      setEditEntry(null);
      await load();
      Alert.alert("Saved", "Clock entry updated.");
    } catch (e: any) {
      Alert.alert("Failed", e.response?.data?.detail || "Try again");
    }
  };

  const reassignShift = async (shiftId: string, newUserId: string) => {
    try {
      await api.patch(`/shifts/${shiftId}/reassign`, { user_id: newUserId });
      await load();
    } catch (e: any) {
      Alert.alert("Reassign failed", e.response?.data?.detail || "Try again");
    } finally {
      setDragShiftId(null);
      setDropTargetId(null);
    }
  };

  // ---- Roster PDF import ----
  const pickRosterPdf = async () => {
    try {
      const DocumentPicker = require("expo-document-picker");
      const FileSystem = require("expo-file-system");
      const res = await DocumentPicker.getDocumentAsync({
        type: "application/pdf",
        copyToCacheDirectory: true,
      });
      if (res.canceled) return;
      const asset = (res.assets && res.assets[0]) || res;
      const uri = asset.uri || asset.file?.uri;
      const name = asset.name || "roster.pdf";
      let b64: string;
      if (Platform.OS === "web" && asset.file) {
        const ab = await asset.file.arrayBuffer();
        let bin = "";
        const bytes = new Uint8Array(ab);
        for (let i = 0; i < bytes.byteLength; i++) bin += String.fromCharCode(bytes[i]);
        b64 = global.btoa(bin);
      } else {
        b64 = await FileSystem.readAsStringAsync(uri, { encoding: FileSystem.EncodingType.Base64 });
      }
      setRosterFile({ name, base64: b64 });
    } catch (e: any) {
      Alert.alert("Pick PDF failed", String(e?.message || e));
    }
  };

  const parseRoster = async () => {
    if (!rosterFile) return Alert.alert("Pick a PDF first");
    setRosterParsing(true);
    try {
      const { data } = await api.post("/roster/parse", { pdf_base64: rosterFile.base64 });
      // Use backend's `suggested_user_id` as the initial user_id (admin can override)
      const rows = (data.rows || []).map((r: any) => ({
        ...r,
        user_id: r.suggested_user_id || null,
      }));
      setRosterRows(rows);
      const matched = rows.filter((r: any) => r.user_id).length;
      if (!data.count) {
        Alert.alert("No rows found", "The AI couldn't extract any staff rows.");
      } else if (matched) {
        Alert.alert(
          "Parsed",
          `${data.count} rows extracted · ${matched} matched to staff automatically. Review and adjust before publishing.`,
        );
      }
    } catch (e: any) {
      Alert.alert("Parse failed", e.response?.data?.detail || "Try again");
    } finally {
      setRosterParsing(false);
    }
  };

  // Publish the raw PDF for ALL staff to view (no per-staff mapping needed)
  const [pubBusy, setPubBusy] = useState(false);
  const publishPdfForViewing = async () => {
    if (!rosterFile) return Alert.alert("Pick a PDF first");
    const defaultTitle = rosterFile.name?.replace(/\.pdf$/i, "") || `Roster ${new Date().toISOString().slice(0, 10)}`;
    setPubBusy(true);
    try {
      const { data } = await api.post("/published-rosters", {
        title: defaultTitle,
        pdf_base64: rosterFile.base64,
        notify: rosterNotify,
      });
      Alert.alert(
        "Roster published",
        `"${data.title}" is now visible to all staff on their Schedule tab.${rosterNotify ? "\n\nNotifications sent." : ""}`,
      );
      setRosterFile(null);
      setRosterOpen(false);
    } catch (e: any) {
      Alert.alert("Publish failed", e.response?.data?.detail || "Try again");
    } finally {
      setPubBusy(false);
    }
  };

  // ---- Roster Templates (save / load) ----
  const loadRosterTemplates = async () => {
    try {
      const { data } = await api.get("/roster/templates");
      setRosterTemplates(data || []);
    } catch {}
  };

  const saveRosterAsTemplate = async () => {
    const name = (
      typeof window !== "undefined" && (window as any).prompt
        ? (window as any).prompt("Template name (e.g. 'Standard week')")
        : null
    );
    if (!name) return;
    try {
      await api.post("/roster/templates", {
        name,
        rows: rosterRows,
        default_start_time: rosterStartTime,
      });
      await loadRosterTemplates();
      Alert.alert("Saved", `Template '${name}' saved. You can load it next time you open this dialog.`);
    } catch (e: any) {
      Alert.alert("Failed", e.response?.data?.detail || "Try again");
    }
  };

  const applyTemplate = (tpl: any) => {
    setRosterRows((tpl.rows || []).map((r: any) => ({ ...r })));
    if (tpl.default_start_time) setRosterStartTime(tpl.default_start_time);
  };

  const deleteTemplate = async (tid: string) => {
    Alert.alert("Delete template?", "This cannot be undone.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: async () => {
          try {
            await api.delete(`/roster/templates/${tid}`);
            await loadRosterTemplates();
          } catch {}
        },
      },
    ]);
  };

  const updateRosterUser = (idx: number, userId: string | null) => {
    setRosterRows((prev) => prev.map((r, i) => (i === idx ? { ...r, user_id: userId } : r)));
  };

  const updateRosterCell = (idx: number, day: string, value: string) => {
    setRosterRows((prev) => prev.map((r, i) => (i === idx ? { ...r, [day]: value } : r)));
  };

  const publishRoster = async () => {
    if (!rosterWeekStart || !/^\d{4}-\d{2}-\d{2}$/.test(rosterWeekStart)) {
      return Alert.alert("Week start required", "Enter the Monday date as YYYY-MM-DD");
    }
    const mapped = rosterRows.filter((r) => r.user_id);
    if (!mapped.length) return Alert.alert("Nothing to publish", "Map at least one row to a staff member.");
    setRosterPublishing(true);
    try {
      const payload = {
        week_start: rosterWeekStart,
        default_start_time: rosterStartTime,
        notify: rosterNotify,
        rows: mapped.map((r: any) => ({
          user_id: r.user_id,
          days: {
            mon: r.mon || "",
            tue: r.tue || "",
            wed: r.wed || "",
            thu: r.thu || "",
            fri: r.fri || "",
            sat: r.sat || "",
            sun: r.sun || "",
          },
        })),
      };
      const { data } = await api.post("/roster/publish", payload);
      Alert.alert(
        "Roster published",
        `${data.created} shifts created · ${data.deleted} replaced · ${data.notified_user_ids.length} staff notified.`,
      );
      setRosterOpen(false);
      setRosterFile(null);
      setRosterRows([]);
      setRosterWeekStart("");
      await load();
    } catch (e: any) {
      Alert.alert("Publish failed", e.response?.data?.detail || "Try again");
    } finally {
      setRosterPublishing(false);
    }
  };

  const openEditUser = (u: any) => {
    setEditUser(u);
    setEuName(u.name || "");
    setEuEmail(u.email || "");
    setEuPhone(u.phone || "");
    setEuDob(u.dob || "");
    setEuPps(u.pps_number || "");
    setEuStart(u.start_date || "");
    setEuType((u.employment_type as any) || "full_time");
    setEuEnt(String(u.holiday_entitlement ?? 25));
  };

  const saveEditUser = async () => {
    if (!editUser) return;
    if (euDob && !/^\d{4}-\d{2}-\d{2}$/.test(euDob)) return Alert.alert("Invalid DOB", "Use YYYY-MM-DD");
    if (euStart && !/^\d{4}-\d{2}-\d{2}$/.test(euStart)) return Alert.alert("Invalid Start Date", "Use YYYY-MM-DD");
    const ent = parseInt(euEnt, 10);
    if (isNaN(ent) || ent < 0 || ent > 365) return Alert.alert("Invalid Entitlement", "0–365 days");
    try {
      await api.patch(`/users/${editUser.id}`, {
        name: euName || undefined,
        email: euEmail || undefined,
        phone: euPhone,
        dob: euDob,
        pps_number: euPps,
        start_date: euStart,
        employment_type: euType,
        holiday_entitlement: ent,
      });
      setEditUser(null);
      await load();
      Alert.alert("Saved", "Employee profile updated.");
    } catch (e: any) {
      Alert.alert("Failed", e.response?.data?.detail || "Try again");
    }
  };

  const deleteEditEntry = async () => {
    if (!editEntry) return;
    Alert.alert("Delete entry?", "This removes the clock entry permanently.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: async () => {
          try {
            await api.delete(`/clock/entries/${editEntry.id}`);
            setEditEntry(null);
            await load();
          } catch (e: any) {
            Alert.alert("Failed", e.response?.data?.detail || "Try again");
          }
        },
      },
    ]);
  };

  const { width: winW } = useWindowDimensions();
  const [forceDesktop, setForceDesktop] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const isDesktop = forceDesktop || (Platform.OS === "web" && winW >= 1024);

  const tabIcons: Record<string, any> = {
    holidays: "calendar",
    shifts: "clock",
    hours: "watch",
    forms: "file-text",
    "pdf-forms": "file",
    users: "users",
    depots: "map-pin",
    offsite: "alert-circle",
    customers: "briefcase",
    hr: "shield",
  };
  const tabLabels: Record<string, string> = {
    holidays: "Holidays",
    shifts: "Schedule",
    hours: "Hours Sheets",
    forms: "Forms",
    "pdf-forms": "PDF Forms",
    users: "Employees",
    depots: "Depots",
    offsite: `Off-site${offsite.length ? ` · ${offsite.length}` : ""}`,
    customers: "Customers",
    hr: "HR",
  };

  // Compute dashboard metrics for the current view (holidays = pending count etc.)
  const pendingHolidays = holidays.filter((h: any) => h.status === "pending").length;
  const approvedHolidays = holidays.filter((h: any) => h.status === "approved").length;
  const offsiteCount = offsite.length;
  const staffCount = users.filter((u: any) => u.role !== "admin").length;

  return (
    <SafeAreaView style={styles.safe}>
      {isDesktop ? (
        // ====== DESKTOP LAYOUT (Connecteam-style) ======
        <View style={styles.deskRoot}>
          {/* Sidebar */}
          <View style={[styles.sidebar, sidebarCollapsed && styles.sidebarCollapsed]}>
            <View style={[styles.sidebarLogo, sidebarCollapsed && { justifyContent: "center" }]}>
              <View style={styles.logoMark}>
                <Feather name="users" size={18} color="#fff" />
              </View>
              {!sidebarCollapsed && <Text style={styles.logoText}>StaffHub</Text>}
            </View>
            <TouchableOpacity
              testID="toggle-sidebar"
              onPress={() => setSidebarCollapsed((v) => !v)}
              style={[styles.sideNav, { justifyContent: sidebarCollapsed ? "center" : "flex-start", marginBottom: 6 }]}
            >
              <Feather
                name={sidebarCollapsed ? "chevrons-right" : "chevrons-left"}
                size={16}
                color={colors.textMuted}
              />
              {!sidebarCollapsed && (
                <Text style={styles.sideNavText}>Collapse</Text>
              )}
            </TouchableOpacity>
            {!sidebarCollapsed && <Text style={styles.sidebarSection}>MANAGE</Text>}
            {(["holidays", "shifts", "hours", "offsite"] as const).map((t) => (
              <TouchableOpacity
                key={t}
                testID={`admin-tab-${t}`}
                onPress={() => setTab(t)}
                style={[
                  styles.sideNav,
                  tab === t && styles.sideNavActive,
                  sidebarCollapsed && { justifyContent: "center" },
                ]}
              >
                <Feather name={tabIcons[t]} size={16} color={tab === t ? colors.brand : colors.textMuted} />
                {!sidebarCollapsed && (
                  <Text style={[styles.sideNavText, tab === t && styles.sideNavTextActive]}>
                    {tabLabels[t]}
                  </Text>
                )}
              </TouchableOpacity>
            ))}
            {!sidebarCollapsed && <Text style={styles.sidebarSection}>FORMS</Text>}
            {(["forms", "pdf-forms"] as const).map((t) => (
              <TouchableOpacity
                key={t}
                testID={`admin-tab-${t}`}
                onPress={() => setTab(t)}
                style={[
                  styles.sideNav,
                  tab === t && styles.sideNavActive,
                  sidebarCollapsed && { justifyContent: "center" },
                ]}
              >
                <Feather name={tabIcons[t]} size={16} color={tab === t ? colors.brand : colors.textMuted} />
                {!sidebarCollapsed && (
                  <Text style={[styles.sideNavText, tab === t && styles.sideNavTextActive]}>
                    {tabLabels[t]}
                  </Text>
                )}
              </TouchableOpacity>
            ))}
            {!sidebarCollapsed && <Text style={styles.sidebarSection}>ORGANISATION</Text>}
            {(["users", "hr", "depots", "customers"] as const).map((t) => (
              <TouchableOpacity
                key={t}
                testID={`admin-tab-${t}`}
                onPress={() => setTab(t)}
                style={[
                  styles.sideNav,
                  tab === t && styles.sideNavActive,
                  sidebarCollapsed && { justifyContent: "center" },
                ]}
              >
                <Feather name={tabIcons[t]} size={16} color={tab === t ? colors.brand : colors.textMuted} />
                {!sidebarCollapsed && (
                  <Text style={[styles.sideNavText, tab === t && styles.sideNavTextActive]}>
                    {tabLabels[t]}
                  </Text>
                )}
              </TouchableOpacity>
            ))}
            <View style={{ flex: 1 }} />
            <TouchableOpacity
              testID="exit-desktop"
              onPress={() => setForceDesktop(false)}
              style={[styles.sideNav, { marginTop: 12, justifyContent: sidebarCollapsed ? "center" : "flex-start" }]}
            >
              <Feather name="smartphone" size={16} color={colors.textMuted} />
              {!sidebarCollapsed && <Text style={styles.sideNavText}>Mobile view</Text>}
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => router.back()}
              style={[styles.sideNav, sidebarCollapsed && { justifyContent: "center" }]}
            >
              <Feather name="arrow-left" size={16} color={colors.textMuted} />
              {!sidebarCollapsed && <Text style={styles.sideNavText}>Back to App</Text>}
            </TouchableOpacity>
          </View>

          {/* Main content area */}
          <View style={styles.deskMain}>
            <View style={styles.deskTopbar}>
              <Text style={[typography.h2, { color: colors.primary }]}>{tabLabels[tab]}</Text>
              <View style={{ flex: 1 }} />
              <View style={styles.adminBadge}>
                <View style={styles.adminAvatar}>
                  <Text style={{ color: "#fff", fontWeight: "700" }}>
                    {user?.name?.[0]?.toUpperCase() || "A"}
                  </Text>
                </View>
                <View style={{ marginLeft: 8 }}>
                  <Text style={{ fontWeight: "700", color: colors.primary, fontSize: 13 }}>
                    {user?.name}
                  </Text>
                  <Text style={[typography.small, { fontSize: 11, color: colors.textMuted }]}>
                    Admin
                  </Text>
                </View>
              </View>
            </View>

            {/* Metric strip */}
            <View style={styles.deskMetrics}>
              <DeskMetric label="Pending holidays" value={pendingHolidays} accent={colors.brand} icon="calendar" />
              <DeskMetric label="Approved" value={approvedHolidays} accent={colors.success} icon="check-circle" />
              <DeskMetric label="Off-site clock-ins" value={offsiteCount} accent={colors.alert} icon="alert-circle" />
              <DeskMetric label="Staff" value={staffCount} accent={colors.primary as any} icon="users" />
            </View>

            <ScrollView contentContainerStyle={styles.deskContent}>
              {renderTabContent()}
            </ScrollView>
          </View>
        </View>
      ) : (
        // ====== MOBILE LAYOUT (existing) ======
        <>
          <View style={styles.header}>
            <TouchableOpacity onPress={() => router.back()}>
              <Feather name="x" size={24} color={colors.primary} />
            </TouchableOpacity>
            <Text style={[typography.h3, { marginLeft: 12, flex: 1 }]}>Admin Panel</Text>
            {Platform.OS === "web" ? (
              <TouchableOpacity
                testID="toggle-desktop"
                onPress={() => setForceDesktop(true)}
                style={styles.desktopToggle}
              >
                <Feather name="monitor" size={14} color={colors.brand} />
                <Text style={{ color: colors.brand, fontSize: 12, fontWeight: "700", marginLeft: 4 }}>
                  Desktop view
                </Text>
              </TouchableOpacity>
            ) : null}
          </View>

          <View style={styles.tabs}>
            {(["holidays", "shifts", "hours", "forms", "pdf-forms", "users", "hr", "depots", "offsite", "customers"] as const).map((t) => (
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
            {renderTabContent()}
          </ScrollView>
        </>
      )}
    </SafeAreaView>
  );

  function renderTabContent() {
    return (
      <>
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
                <TouchableOpacity
                  key={h.id}
                  style={styles.card}
                  testID={`admin-holiday-${h.id}`}
                  activeOpacity={0.7}
                  onPress={() => openHolidayDetail(h)}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontWeight: "700", color: colors.primary }}>{h.user_name}</Text>
                    <Text style={typography.small}>
                      {h.start_date} → {h.end_date} · {h.type}
                      {h.days ? ` · ${h.days}d` : ""}
                    </Text>
                    {h.reason ? <Text style={typography.small}>{h.reason}</Text> : null}
                    <Text style={[typography.small, { marginTop: 4, fontWeight: "700" }]}>{h.status?.toUpperCase()}</Text>
                    {h.status === "cancelled" && h.cancelled_by ? (
                      <Text style={[typography.small, { color: colors.textMuted, fontSize: 11 }]}>
                        by {h.cancelled_by === "admin" ? h.cancelled_by_name || "admin" : "staff"}
                      </Text>
                    ) : null}
                  </View>
                  <View style={{ gap: 6 }}>
                    {h.status === "pending" && (
                      <>
                        <TouchableOpacity testID={`approve-${h.id}`} style={[styles.smBtn, { backgroundColor: colors.success }]} onPress={() => decideHoliday(h.id, "approved")}>
                          <Feather name="check" size={14} color="#fff" />
                        </TouchableOpacity>
                        <TouchableOpacity testID={`reject-${h.id}`} style={[styles.smBtn, { backgroundColor: colors.alert }]} onPress={() => decideHoliday(h.id, "rejected")}>
                          <Feather name="x" size={14} color="#fff" />
                        </TouchableOpacity>
                      </>
                    )}
                    {(h.status === "pending" || h.status === "approved") && (
                      <TouchableOpacity
                        testID={`cancel-h-${h.id}`}
                        style={[styles.smBtn, { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.alert }]}
                        onPress={() => cancelHoliday(h)}
                      >
                        <Feather name="x-circle" size={12} color={colors.alert} />
                        <Text style={{ color: colors.alert, fontSize: 10, fontWeight: "700", marginLeft: 3 }}>
                          Cancel
                        </Text>
                      </TouchableOpacity>
                    )}
                  </View>
                </TouchableOpacity>
              ))
            )}
          </>
        )}

        {tab === "shifts" && (
          <>
            <View style={{ flexDirection: "row", gap: 8 }}>
              <TouchableOpacity style={[styles.addCta, { flex: 1 }]} onPress={() => setShiftModal(true)}>
                <Feather name="plus" size={16} color="#fff" />
                <Text style={styles.addCtaText}>Assign New Shift</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="import-roster-btn"
                style={[styles.addCta, { flex: 1, backgroundColor: colors.brand }]}
                onPress={() => {
                  setRosterOpen(true);
                  loadRosterTemplates();
                }}
              >
                <Feather name="upload" size={16} color="#fff" />
                <Text style={styles.addCtaText}>Import Roster PDF</Text>
              </TouchableOpacity>
            </View>

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
            {isDesktop && (
              <View style={styles.dropZoneStrip} testID="reassign-zone">
                <Text style={[typography.small, { color: colors.textMuted, fontWeight: "600", fontSize: 11, marginRight: 8 }]}>
                  REASSIGN BY DRAG →
                </Text>
                {users.filter((u) => u.role !== "admin").map((u) => {
                  const active = dropTargetId === u.id;
                  return (
                    <View
                      key={u.id}
                      testID={`drop-user-${u.id}`}
                      // @ts-ignore — RN-Web passes DOM props through View
                      onDragOver={(e: any) => {
                        e.preventDefault();
                        if (dropTargetId !== u.id) setDropTargetId(u.id);
                      }}
                      onDragLeave={() => {
                        if (dropTargetId === u.id) setDropTargetId(null);
                      }}
                      onDrop={(e: any) => {
                        e.preventDefault();
                        const sid =
                          (e.dataTransfer && e.dataTransfer.getData("text/plain")) || dragShiftId;
                        if (sid) reassignShift(sid, u.id);
                      }}
                      style={[styles.dropChip, active && styles.dropChipActive]}
                    >
                      <Feather
                        name="user"
                        size={12}
                        color={active ? "#fff" : colors.brand}
                      />
                      <Text
                        style={{
                          marginLeft: 4,
                          color: active ? "#fff" : colors.brand,
                          fontWeight: "700",
                          fontSize: 12,
                        }}
                      >
                        {u.name}
                      </Text>
                    </View>
                  );
                })}
              </View>
            )}
            {allShifts.map((s) => (
              <TouchableOpacity
                key={s.id}
                style={[styles.card, dragShiftId === s.id && { opacity: 0.5 }]}
                testID={`admin-shift-${s.id}`}
                activeOpacity={0.7}
                // @ts-ignore — DOM drag props on web only
                draggable={isDesktop}
                onDragStart={isDesktop ? ((e: any) => {
                  setDragShiftId(s.id);
                  try {
                    if (e.dataTransfer) {
                      e.dataTransfer.effectAllowed = "move";
                      e.dataTransfer.setData("text/plain", s.id);
                    }
                  } catch {}
                }) : undefined}
                onDragEnd={isDesktop ? (() => {
                  setDragShiftId(null);
                  setDropTargetId(null);
                }) : undefined}
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

        {tab === "hours" && (
          <>
            <View style={hsStyles.controls}>
              <TouchableOpacity testID="hours-prev-week" onPress={() => shiftHoursWeek(-7)} style={hsStyles.weekNav}>
                <Feather name="chevron-left" size={16} color={colors.primary} />
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Prev</Text>
              </TouchableOpacity>
              <View style={{ flex: 1, alignItems: "center" }}>
                <Text style={typography.label}>Week</Text>
                <Text style={[typography.h3, { marginTop: 2 }]}>
                  {hoursData?.week_start || "…"} → {hoursData?.week_end || "…"}
                </Text>
              </View>
              <TouchableOpacity testID="hours-next-week" onPress={() => shiftHoursWeek(7)} style={hsStyles.weekNav}>
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Next</Text>
                <Feather name="chevron-right" size={16} color={colors.primary} />
              </TouchableOpacity>
            </View>

            <View style={{ flexDirection: "row", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
              <TouchableOpacity
                testID="hours-this-week"
                onPress={() => { setHoursWeek(""); loadHours(""); }}
                style={[hsStyles.pill, { backgroundColor: colors.brandSoft }]}
              >
                <Text style={{ color: colors.brand, fontWeight: "700" }}>This week</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="hours-refresh"
                onPress={() => loadHours()}
                style={[hsStyles.pill, { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }]}
              >
                <Feather name="refresh-cw" size={13} color={colors.primary} />
                <Text style={{ color: colors.primary, fontWeight: "700", marginLeft: 6 }}>Refresh</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="hours-export-csv"
                onPress={exportHoursCsv}
                style={[hsStyles.pill, { backgroundColor: colors.success }]}
              >
                <Feather name="download" size={13} color="#fff" />
                <Text style={{ color: "#fff", fontWeight: "700", marginLeft: 6 }}>Export CSV</Text>
              </TouchableOpacity>
            </View>

            {hoursLoading && !hoursData && (
              <Text style={[typography.body, { textAlign: "center", padding: spacing.lg }]}>Loading…</Text>
            )}

            {hoursData && hoursData.rows && hoursData.rows.length > 0 && (
              <>
                <View style={hsStyles.summaryRow}>
                  <View style={hsStyles.summaryCell}>
                    <Text style={typography.label}>STAFF</Text>
                    <Text style={[typography.h2, { marginTop: 2 }]}>{hoursData.totals.staff_count}</Text>
                  </View>
                  <View style={hsStyles.summaryCell}>
                    <Text style={typography.label}>TOTAL HOURS</Text>
                    <Text style={[typography.h2, { marginTop: 2 }]}>{hoursData.totals.total_hours}</Text>
                  </View>
                  <View style={hsStyles.summaryCell}>
                    <Text style={typography.label}>NET (AFTER BREAKS)</Text>
                    <Text style={[typography.h2, { marginTop: 2 }]}>{hoursData.totals.net_hours}</Text>
                  </View>
                  <View style={hsStyles.summaryCell}>
                    <Text style={typography.label}>HOLIDAY ACCRUED</Text>
                    <Text style={[typography.h2, { marginTop: 2 }]}>{hoursData.totals.accrued_holiday_hours}</Text>
                  </View>
                </View>

                <View style={hsStyles.tableHeader}>
                  <Text style={[hsStyles.thName]}>Employee</Text>
                  {["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].map(d => (
                    <Text key={d} style={hsStyles.thDay}>{d}</Text>
                  ))}
                  <Text style={hsStyles.thTotal}>Total</Text>
                </View>

                {hoursData.rows.map((r: any) => (
                  <TouchableOpacity
                    key={r.user_id}
                    testID={`hours-row-${r.user_id}`}
                    onPress={() => loadHoursDetail(r.user_id)}
                    style={hsStyles.row}
                  >
                    <View style={hsStyles.tdName}>
                      <Text style={{ fontWeight: "700", color: colors.textPrimary }} numberOfLines={1}>
                        {r.name}
                      </Text>
                      <Text style={{ fontSize: 11, color: colors.textMuted }} numberOfLines={1}>
                        {r.employment_type === "part_time" ? "Part-time" : "Full-time"}
                        {r.has_open_entry ? " · 🟢 currently clocked in" : ""}
                      </Text>
                    </View>
                    {r.days.map((d: any) => (
                      <Text
                        key={d.date}
                        style={[hsStyles.tdDay, d.hours > 0 && { color: colors.textPrimary, fontWeight: "600" }]}
                      >
                        {d.hours > 0 ? d.hours.toFixed(1) : "—"}
                      </Text>
                    ))}
                    <Text style={hsStyles.tdTotal}>{r.total_hours}h</Text>
                  </TouchableOpacity>
                ))}

                <Text style={[typography.small, { color: colors.textMuted, marginTop: 12, textAlign: "center" }]}>
                  Tap any row to view + edit individual clock entries · Hours net of 30-min break per 8h worked · Holiday accrual = 1h per 3h net
                </Text>
              </>
            )}

            {hoursData && hoursData.rows && hoursData.rows.length === 0 && (
              <Text style={[typography.body, { textAlign: "center", padding: spacing.lg, color: colors.textMuted }]}>
                No active staff to report on.
              </Text>
            )}
          </>
        )}

        {tab === "forms" && (
          <>
            {/* A2: Inbox / Templates segmented control */}
            <View style={styles.formsSegmentRow}>
              <TouchableOpacity
                testID="forms-view-inbox"
                style={[styles.formsSegBtn, formsView === "inbox" && styles.formsSegBtnActive]}
                onPress={() => setFormsView("inbox")}
              >
                <Feather name="inbox" size={14} color={formsView === "inbox" ? "#fff" : colors.primary} />
                <Text style={[styles.formsSegBtnText, formsView === "inbox" && { color: "#fff" }]}>
                  Inbox{inboxUnreviewedCount > 0 ? ` · ${inboxUnreviewedCount} new` : ""}
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="forms-view-templates"
                style={[styles.formsSegBtn, formsView === "templates" && styles.formsSegBtnActive]}
                onPress={() => setFormsView("templates")}
              >
                <Feather name="layout" size={14} color={formsView === "templates" ? "#fff" : colors.primary} />
                <Text style={[styles.formsSegBtnText, formsView === "templates" && { color: "#fff" }]}>
                  Templates
                </Text>
              </TouchableOpacity>
            </View>

            {formsView === "inbox" ? (
              <>
                {/* Filter bar */}
                <View style={styles.inboxFilterBar}>
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
                    {/* Kind filter */}
                    <View style={styles.filterGroup}>
                      <Text style={styles.filterLabel}>Type</Text>
                      <View style={{ flexDirection: "row", gap: 4 }}>
                        {(["all", "form", "pdf"] as const).map((k) => (
                          <TouchableOpacity
                            key={k}
                            testID={`inbox-kind-${k}`}
                            onPress={() => setFxKind(k)}
                            style={[styles.filterChip, fxKind === k && styles.filterChipActive]}
                          >
                            <Text style={[styles.filterChipText, fxKind === k && { color: "#fff" }]}>
                              {k === "all" ? "All" : k === "form" ? "Form" : "PDF"}
                            </Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                    </View>
                    {/* Reviewed filter */}
                    <View style={styles.filterGroup}>
                      <Text style={styles.filterLabel}>Status</Text>
                      <View style={{ flexDirection: "row", gap: 4 }}>
                        {([
                          ["all", "All"],
                          ["false", "Unreviewed"],
                          ["true", "Reviewed"],
                        ] as const).map(([v, l]) => (
                          <TouchableOpacity
                            key={v}
                            testID={`inbox-reviewed-${v}`}
                            onPress={() => setFxReviewed(v)}
                            style={[styles.filterChip, fxReviewed === v && styles.filterChipActive]}
                          >
                            <Text style={[styles.filterChipText, fxReviewed === v && { color: "#fff" }]}>
                              {l}
                            </Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                    </View>
                  </View>
                  {/* Template, Staff, Date filters */}
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
                    {/* Template picker */}
                    <View style={[styles.filterGroup, { flex: 1, minWidth: 180 }]}>
                      <Text style={styles.filterLabel}>Form template</Text>
                      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 4 }}>
                        <TouchableOpacity
                          testID="inbox-tpl-all"
                          onPress={() => setFxTemplate("")}
                          style={[styles.filterChip, !fxTemplate && styles.filterChipActive]}
                        >
                          <Text style={[styles.filterChipText, !fxTemplate && { color: "#fff" }]}>All</Text>
                        </TouchableOpacity>
                        {inboxTemplateOptions.map((o) => (
                          <TouchableOpacity
                            key={o.id}
                            testID={`inbox-tpl-${o.id}`}
                            onPress={() => setFxTemplate(fxTemplate === o.id ? "" : o.id)}
                            style={[styles.filterChip, fxTemplate === o.id && styles.filterChipActive]}
                          >
                            <Feather
                              name={o.kind === "pdf" ? "file-text" : "check-square"}
                              size={11}
                              color={fxTemplate === o.id ? "#fff" : colors.textMuted}
                              style={{ marginRight: 4 }}
                            />
                            <Text
                              numberOfLines={1}
                              style={[styles.filterChipText, fxTemplate === o.id && { color: "#fff" }, { maxWidth: 160 }]}
                            >
                              {o.title}
                            </Text>
                          </TouchableOpacity>
                        ))}
                      </ScrollView>
                    </View>
                    {/* Staff picker */}
                    <View style={[styles.filterGroup, { flex: 1, minWidth: 180 }]}>
                      <Text style={styles.filterLabel}>Staff</Text>
                      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 4 }}>
                        <TouchableOpacity
                          testID="inbox-user-all"
                          onPress={() => setFxUser("")}
                          style={[styles.filterChip, !fxUser && styles.filterChipActive]}
                        >
                          <Text style={[styles.filterChipText, !fxUser && { color: "#fff" }]}>All</Text>
                        </TouchableOpacity>
                        {users.filter((u: any) => u.role !== "admin").map((u: any) => (
                          <TouchableOpacity
                            key={u.id}
                            testID={`inbox-user-${u.id}`}
                            onPress={() => setFxUser(fxUser === u.id ? "" : u.id)}
                            style={[styles.filterChip, fxUser === u.id && styles.filterChipActive]}
                          >
                            <Text style={[styles.filterChipText, fxUser === u.id && { color: "#fff" }]}>
                              {u.name}
                            </Text>
                          </TouchableOpacity>
                        ))}
                      </ScrollView>
                    </View>
                  </View>
                  {/* Date range */}
                  <View style={{ flexDirection: "row", gap: 8, marginTop: 10 }}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.filterLabel}>From (YYYY-MM-DD)</Text>
                      <TextInput
                        testID="inbox-from"
                        style={styles.filterInput}
                        value={fxFrom}
                        onChangeText={setFxFrom}
                        placeholder="2026-01-01"
                        placeholderTextColor={colors.textMuted}
                      />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.filterLabel}>To (YYYY-MM-DD)</Text>
                      <TextInput
                        testID="inbox-to"
                        style={styles.filterInput}
                        value={fxTo}
                        onChangeText={setFxTo}
                        placeholder="2026-12-31"
                        placeholderTextColor={colors.textMuted}
                      />
                    </View>
                    <TouchableOpacity
                      testID="inbox-clear-filters"
                      onPress={() => {
                        setFxTemplate(""); setFxUser(""); setFxFrom(""); setFxTo("");
                        setFxReviewed("all"); setFxKind("all");
                      }}
                      style={{
                        alignSelf: "flex-end",
                        height: 40,
                        paddingHorizontal: 14,
                        borderRadius: radius.pill,
                        backgroundColor: colors.surface,
                        alignItems: "center",
                        justifyContent: "center",
                        flexDirection: "row",
                        gap: 4,
                      }}
                    >
                      <Feather name="x" size={13} color={colors.textMuted} />
                      <Text style={{ fontSize: 12, fontWeight: "600", color: colors.textMuted }}>Clear</Text>
                    </TouchableOpacity>
                  </View>
                </View>

                {/* Submissions list */}
                {inboxLoading ? (
                  <Text style={[typography.small, { marginTop: 16, textAlign: "center", color: colors.textMuted }]}>
                    Loading submissions…
                  </Text>
                ) : inbox.length === 0 ? (
                  <View style={{ alignItems: "center", paddingVertical: 32 }}>
                    <Feather name="inbox" size={48} color={colors.textMuted} />
                    <Text style={[typography.small, { marginTop: 8, color: colors.textMuted }]}>
                      No submissions match your filters.
                    </Text>
                  </View>
                ) : (
                  inbox.map((row) => (
                    <View key={`${row.kind}-${row.id}`} style={[styles.card, !row.reviewed && styles.inboxCardUnreviewed]} testID={`inbox-row-${row.id}`}>
                      <View
                        style={[
                          styles.smBtn,
                          {
                            backgroundColor: row.kind === "pdf" ? "#FEE2E2" : colors.brandSoft,
                            width: 36,
                            height: 36,
                            borderRadius: 18,
                          },
                        ]}
                      >
                        <Feather
                          name={row.kind === "pdf" ? "file-text" : "check-square"}
                          size={16}
                          color={row.kind === "pdf" ? "#B91C1C" : colors.brand}
                        />
                      </View>
                      <View style={{ flex: 1, marginLeft: 10 }}>
                        <Text style={{ fontWeight: "700", color: colors.primary }}>{row.template_title || "Untitled form"}</Text>
                        <Text style={typography.small}>
                          <Feather name="user" size={11} color={colors.textMuted} /> {row.user_name || "Unknown"} ·{" "}
                          <Feather name="clock" size={11} color={colors.textMuted} />{" "}
                          {row.created_at ? new Date(row.created_at).toLocaleString() : "—"}
                        </Text>
                        {row.reviewed && row.reviewed_by_name && (
                          <Text style={[typography.small, { marginTop: 2, color: "#0F766E", fontWeight: "600" }]}>
                            <Feather name="check-circle" size={11} color="#0F766E" /> Reviewed by {row.reviewed_by_name}
                            {row.reviewed_at ? ` · ${new Date(row.reviewed_at).toLocaleDateString()}` : ""}
                          </Text>
                        )}
                      </View>
                      <TouchableOpacity
                        testID={`inbox-review-${row.id}`}
                        onPress={() => toggleReviewed(row)}
                        style={[
                          styles.reviewedToggle,
                          row.reviewed ? styles.reviewedToggleOn : styles.reviewedToggleOff,
                        ]}
                      >
                        <Feather
                          name={row.reviewed ? "check-circle" : "circle"}
                          size={13}
                          color={row.reviewed ? "#fff" : colors.textMuted}
                        />
                        <Text
                          style={[
                            { fontSize: 11, fontWeight: "700", marginLeft: 4 },
                            { color: row.reviewed ? "#fff" : colors.textMuted },
                          ]}
                        >
                          {row.reviewed ? "Reviewed" : "Mark reviewed"}
                        </Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        testID={`inbox-download-${row.id}`}
                        onPress={() => downloadSubmission(row)}
                        disabled={inboxDownloading === row.id}
                        style={[
                          styles.smBtn,
                          {
                            backgroundColor: colors.brand,
                            width: 40,
                            height: 40,
                            borderRadius: 20,
                            marginLeft: 6,
                            opacity: inboxDownloading === row.id ? 0.5 : 1,
                          },
                        ]}
                      >
                        <Feather name="download" size={15} color="#fff" />
                      </TouchableOpacity>
                    </View>
                  ))
                )}
              </>
            ) : (
              <>
                {/* Templates management — original Forms tab content */}
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
              pdfTemplates.map((t) => {
                const assigned: string[] = t.assigned_user_ids || [];
                const visible = assigned.length === 0 ? "All staff" : `${assigned.length} staff`;
                return (
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
                    <Text style={[typography.small, { marginTop: 2, color: assigned.length === 0 ? colors.textMuted : colors.brand, fontWeight: "600" }]}>
                      <Feather name="users" size={11} color={assigned.length === 0 ? colors.textMuted : colors.brand} />{"  "}
                      Assigned: {visible}
                    </Text>
                  </View>
                  <TouchableOpacity
                    testID={`pdf-assign-${t.id}`}
                    onPress={() => setAssignModalFor({ ...t, assigned_user_ids: assigned })}
                    style={{ paddingHorizontal: 10, paddingVertical: 6, backgroundColor: colors.brandSoft, borderRadius: 999, marginRight: 6 }}
                  >
                    <Text style={{ fontSize: 11, fontWeight: "700", color: colors.brand }}>Assign</Text>
                  </TouchableOpacity>
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
                );
              })
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
              <View key={u.id} style={styles.card} testID={`user-${u.id}`}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontWeight: "700", color: colors.primary }}>{u.name}</Text>
                  <Text style={typography.small}>{u.email} · {u.role}</Text>
                  <Text style={[typography.small, { marginTop: 2 }]}>
                    <Feather name="calendar" size={11} color={colors.textMuted} /> Entitlement: {u.holiday_entitlement ?? 25} days
                    {"  ·  "}
                    <Feather name="briefcase" size={11} color={colors.textMuted} /> {u.employment_type ? u.employment_type.replace("_", "-") : "type not set"}
                  </Text>
                  {u.start_date ? (
                    <Text style={[typography.small, { marginTop: 1, color: colors.textMuted }]}>Started {u.start_date}</Text>
                  ) : null}
                </View>
                <TouchableOpacity
                  testID={`edit-user-${u.id}`}
                  style={[styles.smBtn, { backgroundColor: colors.brandSoft, width: 56, borderRadius: 14 }]}
                  onPress={() => openEditUser(u)}
                >
                  <Feather name="edit-2" size={14} color={colors.brand} />
                  <Text style={{ color: colors.brand, fontSize: 11, fontWeight: "700", marginLeft: 4 }}>Edit</Text>
                </TouchableOpacity>
              </View>
            ))}
          </>
        )}

        {tab === "depots" && (
          <>
            <TouchableOpacity testID="open-depot-modal" style={styles.addCta} onPress={() => setDepotModal(true)}>
              <Feather name="map-pin" size={16} color="#fff" />
              <Text style={styles.addCtaText}>Add Standalone Depot</Text>
            </TouchableOpacity>
            <Text style={[typography.small, { marginTop: 8, marginBottom: 4 }]}>
              Geofences: clock-ins outside any depot's radius are flagged "off-site" and notify all admins.
              {"\n"}Customer locations appear here automatically once their address/eircode is geocoded.
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

            {allDepots.length === 0 && (
              <Text style={[typography.body, { textAlign: "center", padding: spacing.lg, color: colors.textMuted }]}>
                No depots or customer locations yet. Add a depot above, or add a customer with an eircode/address.
              </Text>
            )}

            {allDepots.map((d) => {
              const isCustomer = d.source === "customer" || d.source === "customer_site";
              const hasCoords = d.lat != null && d.lng != null;
              return (
                <View key={d.id} style={styles.card} testID={`depot-${d.id}`}>
                  <View
                    style={[
                      styles.smBtn,
                      {
                        backgroundColor: isCustomer ? "#FEF3C7" : colors.brandSoft,
                        width: 36, height: 36, borderRadius: 18,
                      },
                    ]}
                  >
                    <Feather
                      name={isCustomer ? "briefcase" : "map-pin"}
                      size={16}
                      color={isCustomer ? "#B45309" : colors.brand}
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                      <Text style={{ fontWeight: "700", color: colors.primary }}>{d.name}</Text>
                      {isCustomer && (
                        <View style={{ paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4, backgroundColor: "#FEF3C7" }}>
                          <Text style={{ fontSize: 10, fontWeight: "700", color: "#B45309" }}>
                            {d.source === "customer_site" ? "CUSTOMER SITE" : "CUSTOMER"}
                          </Text>
                        </View>
                      )}
                    </View>
                    {hasCoords ? (
                      <Text style={typography.small}>
                        {d.lat.toFixed(4)}, {d.lng.toFixed(4)} · {d.radius_m}m radius
                        {d.eircode ? ` · ${d.eircode}` : ""}
                      </Text>
                    ) : (
                      <Text style={[typography.small, { color: colors.alert }]}>
                        ⚠ No GPS yet · {d.eircode || d.address || "no address"} · tap 📍 to geocode
                      </Text>
                    )}
                  </View>

                  {/* Open in Maps */}
                  <TouchableOpacity
                    testID={`depot-maps-${d.id}`}
                    onPress={() =>
                      hasCoords
                        ? openInMaps(d.lat, d.lng, d.name)
                        : openMapsAddress(d.eircode || d.address)
                    }
                    style={[styles.smBtn, { marginRight: 4 }]}
                  >
                    <Feather name="external-link" size={14} color={colors.brand} />
                  </TouchableOpacity>

                  {/* Customer entries can't be deleted here — go to Customers tab. Standalone depots can be deleted. */}
                  {d.source === "depot" ? (
                    <TouchableOpacity onPress={async () => { await api.delete(`/depots/${d.id}`); await load(); }}>
                      <Feather name="trash-2" size={14} color={colors.alert} />
                    </TouchableOpacity>
                  ) : !hasCoords ? (
                    <TouchableOpacity
                      testID={`depot-geocode-${d.id}`}
                      onPress={async () => {
                        try {
                          if (d.source === "customer") {
                            await api.post(`/customers/${d.customer_id}/geocode`);
                          } else {
                            await api.post(`/customers/${d.customer_id}/sites/${d.site_id}/geocode`);
                          }
                          await load();
                          Alert.alert("Geocoded", "Coordinates have been added.");
                        } catch (e: any) {
                          Alert.alert("Couldn't geocode", e.response?.data?.detail || "Try a more specific address.");
                        }
                      }}
                    >
                      <Feather name="navigation" size={14} color={colors.success} />
                    </TouchableOpacity>
                  ) : (
                    <View style={{ width: 14 }} />
                  )}
                </View>
              );
            })}
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
                      style={[styles.smBtn, { backgroundColor: colors.brand, width: 56, borderRadius: 14 }]}
                    >
                      <Feather name="map" size={14} color="#fff" />
                      <Text style={{ color: "#fff", fontSize: 11, fontWeight: "700", marginLeft: 4 }}>Map</Text>
                    </TouchableOpacity>
                  )}
                  <TouchableOpacity
                    testID={`edit-entry-${e.id}`}
                    onPress={() => openEditEntry(e)}
                    style={[styles.smBtn, { backgroundColor: colors.brandSoft, width: 56, borderRadius: 14, marginLeft: 6 }]}
                  >
                    <Feather name="edit-2" size={14} color={colors.brand} />
                    <Text style={{ color: colors.brand, fontSize: 11, fontWeight: "700", marginLeft: 4 }}>Edit</Text>
                  </TouchableOpacity>
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
              Crew tap a customer to view contacts, sites, Eircode + Google Maps, and notes. Staff can read & add notes.
            </Text>
            {/* A4: Alphabetical sectioned list */}
            {(() => {
              const sorted = [...customers].sort((a: any, b: any) =>
                (a.name || "").localeCompare(b.name || "", undefined, { sensitivity: "base" })
              );
              const groups: Record<string, any[]> = {};
              sorted.forEach((c: any) => {
                const letter = (c.name || "?").trim().charAt(0).toUpperCase() || "#";
                const key = /[A-Z]/.test(letter) ? letter : "#";
                if (!groups[key]) groups[key] = [];
                groups[key].push(c);
              });
              const letters = Object.keys(groups).sort();
              return letters.map((L) => (
                <View key={L}>
                  <Text style={styles.azSectionHeader} testID={`az-section-${L}`}>{L}</Text>
                  {groups[L].map((c: any) => (
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
                        {(c.address || c.eircode) ? (
                          <Text style={[typography.small, { marginTop: 2, color: colors.textMuted }]} numberOfLines={1}>
                            <Feather name="map-pin" size={11} color={colors.textMuted} /> {c.address || ""}{c.eircode ? `  ${c.eircode}` : ""}
                          </Text>
                        ) : null}
                      </View>
                      <Feather name="chevron-right" size={16} color={colors.textMuted} />
                    </TouchableOpacity>
                  ))}
                </View>
              ));
            })()}
          </>
        )}

        {tab === "hr" && (
          <>
            <Text style={[typography.label, { marginBottom: 4 }]}>HR — DocuSign replacement</Text>
            <Text style={[typography.small, { marginBottom: 8 }]}>
              Click a staff member to view their HR profile (personal details, holiday balance, assigned documents).
              Issue PDF documents that require read + signature; audit trail captures who signed, when, IP, and device.
            </Text>
            {(() => {
              const sorted = [...hrStaff].sort((a: any, b: any) =>
                (a.name || "").localeCompare(b.name || "", undefined, { sensitivity: "base" })
              );
              const groups: Record<string, any[]> = {};
              sorted.forEach((u: any) => {
                const letter = (u.name || "?").trim().charAt(0).toUpperCase() || "#";
                const key = /[A-Z]/.test(letter) ? letter : "#";
                if (!groups[key]) groups[key] = [];
                groups[key].push(u);
              });
              const letters = Object.keys(groups).sort();
              if (letters.length === 0) {
                return (
                  <Text style={[typography.small, { textAlign: "center", marginTop: 24, color: colors.textMuted }]}>
                    No staff yet.
                  </Text>
                );
              }
              return letters.map((L) => (
                <View key={L}>
                  <Text style={styles.azSectionHeader} testID={`hr-section-${L}`}>{L}</Text>
                  {groups[L].map((u: any) => {
                    const pendSig = u.hr_pending_signature || 0;
                    return (
                      <TouchableOpacity
                        key={u.id}
                        testID={`hr-user-${u.id}`}
                        style={styles.card}
                        onPress={() => setHrActiveUserId(u.id)}
                      >
                        <View style={[styles.smBtn, { backgroundColor: colors.brandSoft, width: 36, height: 36, borderRadius: 18 }]}>
                          <Feather name="user" size={16} color={colors.brand} />
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={{ fontWeight: "700", color: colors.primary }}>{u.name}</Text>
                          <Text style={typography.small}>
                            {u.email} · {u.hr_total || 0} doc{(u.hr_total || 0) === 1 ? "" : "s"}
                          </Text>
                        </View>
                        {pendSig > 0 ? (
                          <View style={{ backgroundColor: colors.alert, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, marginRight: 8 }}>
                            <Text style={{ color: "#fff", fontSize: 10, fontWeight: "800" }}>{pendSig} PENDING</Text>
                          </View>
                        ) : (u.hr_counts?.signed || 0) > 0 ? (
                          <View style={{ backgroundColor: "#0F766E", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, marginRight: 8 }}>
                            <Text style={{ color: "#fff", fontSize: 10, fontWeight: "800" }}>{u.hr_counts?.signed} SIGNED</Text>
                          </View>
                        ) : null}
                        <Feather name="chevron-right" size={16} color={colors.textMuted} />
                      </TouchableOpacity>
                    );
                  })}
                </View>
              ));
            })()}
          </>
        )}

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

      {/* A3: HR Profile drawer */}
      <HRProfileModal
        visible={!!hrActiveUserId}
        userId={hrActiveUserId}
        onClose={() => { setHrActiveUserId(null); loadHrStaff(); }}
        onReload={loadHrStaff}
      />

      {/* New Customer Modal */}
      <Modal visible={newCustomerModal} animationType="slide" transparent onRequestClose={() => setNewCustomerModal(false)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <Text style={typography.h3}>New Customer</Text>
            <TextInput testID="cust-name" style={styles.input} placeholder="Name (e.g. Aer Lingus)" value={ncName} onChangeText={setNcName} placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="Company" value={ncCompany} onChangeText={setNcCompany} placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="Email" value={ncEmail} onChangeText={setNcEmail} autoCapitalize="none" placeholderTextColor={colors.textMuted} />
            <TextInput style={styles.input} placeholder="Phone" value={ncPhone} onChangeText={setNcPhone} placeholderTextColor={colors.textMuted} />
            <TextInput testID="cust-address" style={styles.input} placeholder="Address" value={ncAddress} onChangeText={setNcAddress} placeholderTextColor={colors.textMuted} />
            <TextInput testID="cust-eircode" style={styles.input} placeholder="Eircode (e.g. D02 X285)" value={ncEircode} onChangeText={setNcEircode} autoCapitalize="characters" placeholderTextColor={colors.textMuted} />
            <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
              <TouchableOpacity style={[styles.modalBtn, { backgroundColor: colors.surface }]} onPress={() => setNewCustomerModal(false)}>
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="cust-submit" style={[styles.modalBtn, { backgroundColor: colors.primary }]} onPress={async () => {
                if (!ncName) return Alert.alert("Name required");
                try {
                  const { data } = await api.post("/customers", {
                    name: ncName,
                    company: ncCompany,
                    email: ncEmail,
                    phone: ncPhone,
                    address: ncAddress,
                    eircode: ncEircode,
                  });
                  setNewCustomerModal(false);
                  setNcName(""); setNcCompany(""); setNcEmail(""); setNcPhone("");
                  setNcAddress(""); setNcEircode("");
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
            {/* Assign to staff (multi-select). Empty = visible to ALL */}
            <Text style={[typography.label, { marginTop: 14 }]}>
              <Feather name="users" size={12} /> Assign to staff{" "}
              <Text style={{ color: colors.textMuted, fontWeight: "400" }}>
                ({pdfAssignedIds.length === 0 ? "all staff" : `${pdfAssignedIds.length} selected`})
              </Text>
            </Text>
            <Text style={[typography.small, { marginTop: 2, marginBottom: 6, color: colors.textMuted }]}>
              Leave empty to show this form to every staff member.
            </Text>
            <View style={{ maxHeight: 180, borderRadius: 10, borderWidth: 1, borderColor: colors.border, padding: 6 }}>
              <ScrollView nestedScrollEnabled style={{ maxHeight: 168 }}>
                {users
                  .filter((u) => u.role !== "admin")
                  .map((u) => {
                    const sel = pdfAssignedIds.includes(u.id);
                    return (
                      <TouchableOpacity
                        key={u.id}
                        testID={`assign-user-${u.id}`}
                        onPress={() =>
                          setPdfAssignedIds((prev) =>
                            prev.includes(u.id) ? prev.filter((x) => x !== u.id) : [...prev, u.id]
                          )
                        }
                        style={{
                          flexDirection: "row",
                          alignItems: "center",
                          paddingVertical: 8,
                          paddingHorizontal: 6,
                        }}
                      >
                        <View
                          style={{
                            width: 20,
                            height: 20,
                            borderRadius: 4,
                            borderWidth: 2,
                            borderColor: sel ? colors.brand : colors.border,
                            backgroundColor: sel ? colors.brand : "transparent",
                            alignItems: "center",
                            justifyContent: "center",
                            marginRight: 10,
                          }}
                        >
                          {sel ? <Feather name="check" size={14} color="#fff" /> : null}
                        </View>
                        <Text style={{ flex: 1, color: colors.primary, fontWeight: "600" }}>{u.name}</Text>
                        <Text style={[typography.small, { color: colors.textMuted }]}>{u.email}</Text>
                      </TouchableOpacity>
                    );
                  })}
              </ScrollView>
            </View>
            <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
              <TouchableOpacity
                style={[styles.modalBtn, { backgroundColor: colors.surface }]}
                onPress={() => {
                  setPdfModalOpen(false);
                  setPdfPicked(null);
                  setPdfTitle("");
                  setPdfDesc("");
                  setPdfAssignedIds([]);
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

      {/* Assign existing PDF template to staff */}
      <Modal visible={!!assignModalFor} transparent animationType="slide" onRequestClose={() => setAssignModalFor(null)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <Text style={typography.h3}>Assign to Staff</Text>
            <Text style={[typography.small, { marginTop: 4, marginBottom: 8 }]} numberOfLines={1}>
              {assignModalFor?.title}
            </Text>
            <Text style={[typography.small, { marginBottom: 6, color: colors.textMuted }]}>
              {(assignModalFor?.assigned_user_ids || []).length === 0
                ? "Currently visible to ALL staff."
                : `Currently assigned to ${(assignModalFor?.assigned_user_ids || []).length} staff.`}
            </Text>
            <View style={{ maxHeight: 320, borderRadius: 10, borderWidth: 1, borderColor: colors.border, padding: 6 }}>
              <ScrollView nestedScrollEnabled style={{ maxHeight: 308 }}>
                {users
                  .filter((u) => u.role !== "admin")
                  .map((u) => {
                    const sel = (assignModalFor?.assigned_user_ids || []).includes(u.id);
                    return (
                      <TouchableOpacity
                        key={u.id}
                        testID={`assign-modal-user-${u.id}`}
                        onPress={() => toggleAssign(u.id)}
                        style={{ flexDirection: "row", alignItems: "center", paddingVertical: 10, paddingHorizontal: 6 }}
                      >
                        <View
                          style={{
                            width: 22,
                            height: 22,
                            borderRadius: 4,
                            borderWidth: 2,
                            borderColor: sel ? colors.brand : colors.border,
                            backgroundColor: sel ? colors.brand : "transparent",
                            alignItems: "center",
                            justifyContent: "center",
                            marginRight: 10,
                          }}
                        >
                          {sel ? <Feather name="check" size={14} color="#fff" /> : null}
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={{ color: colors.primary, fontWeight: "600" }}>{u.name}</Text>
                          <Text style={[typography.small, { color: colors.textMuted }]}>{u.email}</Text>
                        </View>
                      </TouchableOpacity>
                    );
                  })}
              </ScrollView>
            </View>
            <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
              <TouchableOpacity
                style={[styles.modalBtn, { backgroundColor: colors.surface }]}
                onPress={() => setAssignModalFor(null)}
              >
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="assign-save"
                style={[styles.modalBtn, { backgroundColor: colors.primary }]}
                onPress={saveAssignment}
              >
                <Text style={{ color: "#fff", fontWeight: "700" }}>Save</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Edit / delete a clock entry (admin override) */}
      <Modal visible={!!editEntry} transparent animationType="slide" onRequestClose={() => setEditEntry(null)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <Text style={typography.h3}>Edit Clock Entry</Text>
            <Text style={[typography.small, { marginTop: 4, marginBottom: 12, color: colors.textMuted }]}>
              {editEntry?.user_name} · {editEntry?.depot_name || "—"}
            </Text>
            <Text style={typography.label}>Clock-In (local time)</Text>
            <TextInput
              testID="edit-clock-in"
              style={styles.input}
              placeholder="YYYY-MM-DDTHH:MM"
              value={editIn}
              onChangeText={setEditIn}
              placeholderTextColor={colors.textMuted}
            />
            <Text style={[typography.label, { marginTop: 8 }]}>Clock-Out (leave blank for open shift)</Text>
            <TextInput
              testID="edit-clock-out"
              style={styles.input}
              placeholder="YYYY-MM-DDTHH:MM"
              value={editOut}
              onChangeText={setEditOut}
              placeholderTextColor={colors.textMuted}
            />
            <Text style={[typography.small, { marginTop: 8, color: colors.textMuted, fontSize: 11 }]}>
              Tip: enter times in the format above (browser local time). Saving recalculates hours and accrual.
            </Text>
            <View style={{ flexDirection: "row", gap: 8, marginTop: 14 }}>
              <TouchableOpacity
                testID="edit-delete"
                style={[styles.modalBtn, { backgroundColor: "#FEE2E2" }]}
                onPress={deleteEditEntry}
              >
                <Feather name="trash-2" size={14} color={colors.alert} />
                <Text style={{ color: colors.alert, fontWeight: "700", marginLeft: 4 }}>Delete</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modalBtn, { backgroundColor: colors.surface }]}
                onPress={() => setEditEntry(null)}
              >
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="edit-save"
                style={[styles.modalBtn, { backgroundColor: colors.primary }]}
                onPress={saveEditEntry}
              >
                <Text style={{ color: "#fff", fontWeight: "700" }}>Save</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Admin: edit full employee profile (Phase 2) */}
      <Modal visible={!!editUser} transparent animationType="slide" onRequestClose={() => setEditUser(null)}>
        <View style={styles.modalBg}>
          <View style={[styles.modalCard, { maxHeight: "92%" }]}>
            <Text style={typography.h3}>Edit Employee</Text>
            <Text style={[typography.small, { color: colors.textMuted, marginTop: 2, marginBottom: 8 }]}>
              {editUser?.email}
            </Text>
            <ScrollView nestedScrollEnabled style={{ maxHeight: 440 }}>
              <Text style={typography.label}>Name</Text>
              <TextInput testID="eu-name" style={styles.input} value={euName} onChangeText={setEuName} />
              <Text style={[typography.label, { marginTop: 8 }]}>Email</Text>
              <TextInput
                testID="eu-email"
                style={styles.input}
                value={euEmail}
                onChangeText={setEuEmail}
                autoCapitalize="none"
                keyboardType="email-address"
              />
              <Text style={[typography.label, { marginTop: 8 }]}>Phone</Text>
              <TextInput testID="eu-phone" style={styles.input} value={euPhone} onChangeText={setEuPhone} keyboardType="phone-pad" />
              <Text style={[typography.label, { marginTop: 8 }]}>Date of Birth (YYYY-MM-DD)</Text>
              <TextInput testID="eu-dob" style={styles.input} value={euDob} onChangeText={setEuDob} placeholder="YYYY-MM-DD" placeholderTextColor={colors.textMuted} />
              <Text style={[typography.label, { marginTop: 8 }]}>PPS Number</Text>
              <TextInput testID="eu-pps" style={styles.input} value={euPps} onChangeText={setEuPps} autoCapitalize="characters" />
              <Text style={[typography.label, { marginTop: 8 }]}>Start Date (employment)</Text>
              <TextInput testID="eu-start" style={styles.input} value={euStart} onChangeText={setEuStart} placeholder="YYYY-MM-DD" placeholderTextColor={colors.textMuted} />
              <Text style={[typography.label, { marginTop: 8 }]}>Employment Type</Text>
              <View style={{ flexDirection: "row", gap: 8, marginTop: 6 }}>
                {(["full_time", "part_time"] as const).map((t) => (
                  <TouchableOpacity
                    key={t}
                    testID={`eu-type-${t}`}
                    onPress={() => setEuType(t)}
                    style={[styles.typeChip, euType === t && { backgroundColor: colors.primary }]}
                  >
                    <Text style={{ color: euType === t ? "#fff" : colors.primary, fontWeight: "600", fontSize: 13 }}>
                      {t.replace("_", "-")}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={[typography.label, { marginTop: 8 }]}>Holiday Entitlement (days/year)</Text>
              <TextInput
                testID="eu-ent"
                style={styles.input}
                value={euEnt}
                onChangeText={setEuEnt}
                keyboardType="number-pad"
              />
              <Text style={[typography.small, { color: colors.textMuted, marginTop: 4, fontSize: 11 }]}>
                Sick-pay eligibility requires 13 continuous weeks from Start Date. Bank holiday is automatic for full-time; part-time needs 40 hrs in last 5 weeks.
              </Text>
            </ScrollView>
            <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
              <TouchableOpacity
                style={[styles.modalBtn, { backgroundColor: colors.surface }]}
                onPress={() => setEditUser(null)}
              >
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="eu-save"
                style={[styles.modalBtn, { backgroundColor: colors.primary }]}
                onPress={saveEditUser}
              >
                <Text style={{ color: "#fff", fontWeight: "700" }}>Save</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Roster PDF import (Schedule) */}
      <Modal visible={rosterOpen} transparent animationType="slide" onRequestClose={() => setRosterOpen(false)}>
        <View style={styles.modalBg}>
          <View style={[styles.modalCard, { maxHeight: "95%", width: "94%", maxWidth: 720 }]}>
            <Text style={typography.h3}>Import Roster PDF</Text>
            <Text style={[typography.small, { color: colors.textMuted, marginTop: 2, marginBottom: 8 }]}>
              Upload a roster PDF — the AI extracts the staff × day grid, you map names → app users and set a start time, then publish.
            </Text>

            {!rosterFile && (
              <TouchableOpacity testID="pick-roster-pdf" onPress={pickRosterPdf} style={styles.rosterPickBtn}>
                <Feather name="upload-cloud" size={22} color={colors.primary} />
                <Text style={{ fontWeight: "700", color: colors.primary, marginTop: 6 }}>
                  Tap to pick a PDF
                </Text>
              </TouchableOpacity>
            )}

            {rosterFile && rosterRows.length === 0 && (
              <View style={styles.rosterPickBtn}>
                <Feather name="file-text" size={22} color={colors.success} />
                <Text style={{ fontWeight: "700", color: colors.primary, marginTop: 6 }} numberOfLines={1}>
                  {rosterFile.name}
                </Text>
                <View style={{ flexDirection: "row", gap: 8, marginTop: 10, flexWrap: "wrap", justifyContent: "center" }}>
                  <TouchableOpacity onPress={() => setRosterFile(null)} style={[styles.modalBtn, { backgroundColor: colors.surface }]}>
                    <Text style={{ color: colors.primary, fontWeight: "700" }}>Re-pick</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    testID="publish-pdf-for-viewing"
                    onPress={publishPdfForViewing}
                    disabled={pubBusy}
                    style={[styles.modalBtn, { backgroundColor: colors.success, opacity: pubBusy ? 0.6 : 1 }]}
                  >
                    <Text style={{ color: "#fff", fontWeight: "700" }}>
                      {pubBusy ? "Publishing…" : "Publish to all staff"}
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    testID="parse-roster"
                    onPress={parseRoster}
                    disabled={rosterParsing}
                    style={[styles.modalBtn, { backgroundColor: colors.brand, opacity: rosterParsing ? 0.6 : 1 }]}
                  >
                    <Text style={{ color: "#fff", fontWeight: "700" }}>
                      {rosterParsing ? "Parsing with AI…" : "Parse with AI"}
                    </Text>
                  </TouchableOpacity>
                </View>
                <Text style={[typography.small, { color: colors.textMuted, marginTop: 10, textAlign: "center", paddingHorizontal: 8 }]}>
                  • Publish: every staff member sees the PDF on their Schedule tab. No per-name mapping needed.{"\n"}
                  • Parse with AI: extract the staff × day grid, map each row to a user, generate individual shifts.
                </Text>
              </View>
            )}

            {rosterRows.length > 0 && (
              <>
                <View style={{ flexDirection: "row", gap: 8, marginTop: 10, marginBottom: 6 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={typography.label}>Monday of the roster week</Text>
                    <TextInput
                      testID="roster-week-start"
                      style={styles.input}
                      value={rosterWeekStart}
                      onChangeText={setRosterWeekStart}
                      placeholder="YYYY-MM-DD"
                      placeholderTextColor={colors.textMuted}
                    />
                  </View>
                  <View style={{ width: 110 }}>
                    <Text style={typography.label}>Start time</Text>
                    <TextInput
                      testID="roster-start-time"
                      style={styles.input}
                      value={rosterStartTime}
                      onChangeText={setRosterStartTime}
                      placeholder="HH:MM"
                      placeholderTextColor={colors.textMuted}
                    />
                  </View>
                </View>
                <TouchableOpacity
                  onPress={() => setRosterNotify((v) => !v)}
                  style={{ flexDirection: "row", alignItems: "center", marginBottom: 6 }}
                >
                  <View
                    style={{
                      width: 20,
                      height: 20,
                      borderRadius: 4,
                      borderWidth: 2,
                      borderColor: rosterNotify ? colors.brand : colors.border,
                      backgroundColor: rosterNotify ? colors.brand : "transparent",
                      alignItems: "center",
                      justifyContent: "center",
                      marginRight: 8,
                    }}
                  >
                    {rosterNotify ? <Feather name="check" size={14} color="#fff" /> : null}
                  </View>
                  <Text style={{ color: colors.primary, fontWeight: "600", fontSize: 13 }}>
                    Notify each staff member when published
                  </Text>
                </TouchableOpacity>

                {/* Save / load templates */}
                <View style={styles.templatesBar}>
                  <Feather name="bookmark" size={12} color={colors.brand} />
                  <Text style={[typography.small, { color: colors.brand, fontWeight: "700", marginLeft: 4, marginRight: 8 }]}>
                    TEMPLATES
                  </Text>
                  {rosterTemplates.length === 0 ? (
                    <Text style={[typography.small, { color: colors.textMuted, fontSize: 11 }]}>
                      No saved templates yet.
                    </Text>
                  ) : (
                    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, flex: 1 }}>
                      {rosterTemplates.map((tpl) => (
                        <View key={tpl.id} style={styles.templatePill}>
                          <TouchableOpacity
                            testID={`load-tpl-${tpl.id}`}
                            onPress={() => applyTemplate(tpl)}
                          >
                            <Text style={{ fontSize: 11, color: colors.brand, fontWeight: "700" }}>
                              {tpl.name}
                            </Text>
                          </TouchableOpacity>
                          <TouchableOpacity onPress={() => deleteTemplate(tpl.id)} style={{ marginLeft: 6 }}>
                            <Feather name="x" size={11} color={colors.alert} />
                          </TouchableOpacity>
                        </View>
                      ))}
                    </View>
                  )}
                  <TouchableOpacity
                    testID="save-tpl-btn"
                    onPress={saveRosterAsTemplate}
                    style={styles.savePillBtn}
                  >
                    <Feather name="save" size={11} color="#fff" />
                    <Text style={{ color: "#fff", fontSize: 11, fontWeight: "700", marginLeft: 3 }}>
                      Save as template
                    </Text>
                  </TouchableOpacity>
                </View>

                <Text style={[typography.small, { color: colors.textMuted, marginTop: 4, marginBottom: 4 }]}>
                  {rosterRows.length} rows parsed. Map a staff user for each row you want to publish; rows with no user are skipped.
                </Text>
                <ScrollView nestedScrollEnabled style={{ maxHeight: 350, borderRadius: 8, borderWidth: 1, borderColor: colors.border }}>
                  {rosterRows.map((r, idx) => (
                    <View key={idx} style={styles.rosterRow}>
                      <View style={{ flex: 1.4 }}>
                        <Text style={{ fontWeight: "700", color: colors.primary, fontSize: 13 }} numberOfLines={1}>
                          {r.name}
                        </Text>
                        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 4, marginTop: 2 }}>
                          {(["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const).map((d) =>
                            r[d] ? (
                              <Text key={d} style={styles.rosterDayPill}>
                                {d.toUpperCase()} · {r[d]}
                              </Text>
                            ) : null,
                          )}
                        </View>
                      </View>
                      <View style={{ width: 140, marginLeft: 8 }}>
                        <ScrollView
                          horizontal={false}
                          nestedScrollEnabled
                          style={{ maxHeight: 100, borderWidth: 1, borderColor: colors.border, borderRadius: 6 }}
                        >
                          <TouchableOpacity
                            onPress={() => updateRosterUser(idx, null)}
                            style={[styles.userPick, !r.user_id && { backgroundColor: colors.brandSoft }]}
                          >
                            <Text style={{ fontSize: 11, color: r.user_id ? colors.textMuted : colors.brand, fontWeight: "600" }}>
                              — Skip row —
                            </Text>
                          </TouchableOpacity>
                          {users
                            .filter((u) => u.role !== "admin")
                            .map((u) => (
                              <TouchableOpacity
                                key={u.id}
                                testID={`roster-map-${idx}-${u.id}`}
                                onPress={() => updateRosterUser(idx, u.id)}
                                style={[styles.userPick, r.user_id === u.id && { backgroundColor: colors.brand }]}
                              >
                                <Text
                                  style={{
                                    fontSize: 11,
                                    color: r.user_id === u.id ? "#fff" : colors.primary,
                                    fontWeight: "600",
                                  }}
                                  numberOfLines={1}
                                >
                                  {u.name}
                                </Text>
                              </TouchableOpacity>
                            ))}
                        </ScrollView>
                      </View>
                    </View>
                  ))}
                </ScrollView>
              </>
            )}

            <View style={{ flexDirection: "row", gap: 8, marginTop: 14 }}>
              <TouchableOpacity
                style={[styles.modalBtn, { backgroundColor: colors.surface }]}
                onPress={() => {
                  setRosterOpen(false);
                  setRosterFile(null);
                  setRosterRows([]);
                  setRosterWeekStart("");
                }}
              >
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Close</Text>
              </TouchableOpacity>
              {rosterRows.length > 0 && (
                <TouchableOpacity
                  testID="publish-roster"
                  style={[styles.modalBtn, { backgroundColor: colors.success, opacity: rosterPublishing ? 0.6 : 1 }]}
                  onPress={publishRoster}
                  disabled={rosterPublishing}
                >
                  <Feather name="send" size={14} color="#fff" />
                  <Text style={{ color: "#fff", fontWeight: "700", marginLeft: 4 }}>
                    {rosterPublishing ? "Publishing…" : "Publish to Staff"}
                  </Text>
                </TouchableOpacity>
              )}
            </View>
          </View>
        </View>
      </Modal>

      {/* A1: Holiday detail modal — view, approve, reject, cancel, edit */}
      <Modal visible={!!holidayDetail} transparent animationType="slide" onRequestClose={() => setHolidayDetail(null)}>
        <View style={styles.modalBg}>
          <View style={[styles.modalCard, { maxHeight: "92%" }]}>
            <View style={{ flexDirection: "row", alignItems: "center" }}>
              <Text style={[typography.h3, { flex: 1 }]}>Holiday Request</Text>
              <View
                style={[
                  styles.statusPill,
                  holidayDetail?.status === "approved" && { backgroundColor: "#D1FAE5" },
                  holidayDetail?.status === "rejected" && { backgroundColor: "#FEE2E2" },
                  holidayDetail?.status === "cancelled" && { backgroundColor: colors.surface },
                ]}
              >
                <Text
                  style={[
                    styles.statusText,
                    holidayDetail?.status === "cancelled" && { color: colors.textMuted },
                  ]}
                >
                  {holidayDetail?.status}
                </Text>
              </View>
            </View>
            <Text style={[typography.small, { marginTop: 4, marginBottom: 8 }]}>
              Submitted by{" "}
              <Text style={{ fontWeight: "700", color: colors.primary }}>{holidayDetail?.user_name}</Text>
              {holidayDetail?.created_at ? ` · ${String(holidayDetail.created_at).slice(0, 10)}` : ""}
              {holidayDetail?.days ? ` · ${holidayDetail.days} day${holidayDetail.days === 1 ? "" : "s"}` : ""}
            </Text>
            <ScrollView nestedScrollEnabled style={{ maxHeight: 440 }}>
              <View style={{ flexDirection: "row", gap: 8 }}>
                {(["annual", "sick", "unpaid"] as const).map((t) => (
                  <TouchableOpacity
                    key={t}
                    onPress={() => setHdType(t)}
                    style={[styles.typeChip, hdType === t && { backgroundColor: colors.primary }]}
                  >
                    <Text style={{ color: hdType === t ? "#fff" : colors.primary, fontWeight: "600", fontSize: 13 }}>
                      {t}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={[typography.label, { marginTop: 10 }]}>Start (YYYY-MM-DD)</Text>
              <TextInput testID="hd-start" style={styles.input} value={hdStart} onChangeText={setHdStart} />
              <Text style={[typography.label, { marginTop: 8 }]}>End (YYYY-MM-DD)</Text>
              <TextInput testID="hd-end" style={styles.input} value={hdEnd} onChangeText={setHdEnd} />
              <Text style={[typography.label, { marginTop: 8 }]}>Reason</Text>
              <TextInput
                testID="hd-reason"
                style={[styles.input, { height: 64 }]}
                value={hdReason}
                onChangeText={setHdReason}
                multiline
                placeholder="Optional"
                placeholderTextColor={colors.textMuted}
              />
              {holidayDetail?.edited_at ? (
                <Text style={[typography.small, { color: colors.textMuted, fontSize: 11, marginTop: 6 }]}>
                  Last edited by {holidayDetail.edited_by_name || holidayDetail.edited_by}{" "}
                  · {String(holidayDetail.edited_at).slice(0, 16)}
                </Text>
              ) : null}
              {holidayDetail?.cancelled_at ? (
                <Text style={[typography.small, { color: colors.alert, fontSize: 11, marginTop: 6 }]}>
                  Cancelled by {holidayDetail.cancelled_by === "admin" ? holidayDetail.cancelled_by_name || "admin" : "staff"}{" "}
                  · {String(holidayDetail.cancelled_at).slice(0, 16)}
                </Text>
              ) : null}
            </ScrollView>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 14 }}>
              <TouchableOpacity
                style={[styles.modalBtn, { backgroundColor: colors.surface, flex: 0, paddingHorizontal: 14 }]}
                onPress={() => setHolidayDetail(null)}
              >
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Close</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="hd-save"
                style={[styles.modalBtn, { backgroundColor: colors.primary, flex: 0, paddingHorizontal: 14 }]}
                onPress={saveHolidayEdit}
              >
                <Feather name="save" size={14} color="#fff" />
                <Text style={{ color: "#fff", fontWeight: "700", marginLeft: 4 }}>Save edits</Text>
              </TouchableOpacity>
              {holidayDetail?.status === "pending" && (
                <>
                  <TouchableOpacity
                    testID="hd-approve"
                    style={[styles.modalBtn, { backgroundColor: colors.success, flex: 0, paddingHorizontal: 14 }]}
                    onPress={() => decideInDetail("approved")}
                  >
                    <Feather name="check" size={14} color="#fff" />
                    <Text style={{ color: "#fff", fontWeight: "700", marginLeft: 4 }}>Approve</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    testID="hd-reject"
                    style={[styles.modalBtn, { backgroundColor: colors.alert, flex: 0, paddingHorizontal: 14 }]}
                    onPress={() => decideInDetail("rejected")}
                  >
                    <Feather name="x" size={14} color="#fff" />
                    <Text style={{ color: "#fff", fontWeight: "700", marginLeft: 4 }}>Reject</Text>
                  </TouchableOpacity>
                </>
              )}
              {(holidayDetail?.status === "pending" || holidayDetail?.status === "approved") && (
                <TouchableOpacity
                  testID="hd-cancel"
                  style={[styles.modalBtn, { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.alert, flex: 0, paddingHorizontal: 14 }]}
                  onPress={cancelInDetail}
                >
                  <Feather name="x-circle" size={14} color={colors.alert} />
                  <Text style={{ color: colors.alert, fontWeight: "700", marginLeft: 4 }}>Cancel request</Text>
                </TouchableOpacity>
              )}
            </View>
          </View>
        </View>
      </Modal>

      {/* Hours Sheets — per-user entry detail */}
      <Modal visible={!!hoursDetailUserId} transparent animationType="slide" onRequestClose={() => { setHoursDetailUserId(null); setHoursDetailEntries([]); }}>
        <View style={styles.modalBg}>
          <View style={[styles.modalCard, { maxHeight: "85%" }]}>
            <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 8 }}>
              <Text style={typography.h3}>
                Clock entries · {hoursData?.rows?.find((r: any) => r.user_id === hoursDetailUserId)?.name || ""}
              </Text>
              <View style={{ flex: 1 }} />
              <TouchableOpacity onPress={() => { setHoursDetailUserId(null); setHoursDetailEntries([]); }}>
                <Feather name="x" size={22} color={colors.primary} />
              </TouchableOpacity>
            </View>
            <Text style={[typography.small, { color: colors.textMuted, marginBottom: 10 }]}>
              Week {hoursData?.week_start} → {hoursData?.week_end}
            </Text>

            <ScrollView style={{ maxHeight: 500 }}>
              {hoursDetailEntries.length === 0 && (
                <Text style={[typography.body, { textAlign: "center", padding: spacing.lg, color: colors.textMuted }]}>
                  No clock entries this week.
                </Text>
              )}
              {hoursDetailEntries.map((e: any) => {
                const cin = e.clock_in ? new Date(e.clock_in) : null;
                const cout = e.clock_out ? new Date(e.clock_out) : null;
                const dur = e.duration_seconds ? (e.duration_seconds / 3600).toFixed(2) : (cout && cin ? ((cout.getTime() - cin.getTime()) / 3600000).toFixed(2) : "—");
                return (
                  <View key={e.id} style={[styles.card, { marginBottom: 6 }]}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontWeight: "700" }}>
                        {cin ? cin.toLocaleString() : "—"}
                      </Text>
                      <Text style={typography.small}>
                        → {cout ? cout.toLocaleString() : "still clocked in"} · {dur}h
                      </Text>
                      {e.off_site ? (
                        <Text style={[typography.small, { color: colors.alert }]}>Off-site clock-in</Text>
                      ) : null}
                      {e.note ? <Text style={typography.small}>Note: {e.note}</Text> : null}
                    </View>
                    <TouchableOpacity
                      onPress={() => setHoursEditEntry({
                        id: e.id,
                        clock_in_iso: e.clock_in ? new Date(e.clock_in).toISOString().slice(0, 16) : "",
                        clock_out_iso: e.clock_out ? new Date(e.clock_out).toISOString().slice(0, 16) : "",
                        note: e.note || "",
                      })}
                      style={styles.smBtn}
                    >
                      <Feather name="edit-2" size={16} color={colors.primary} />
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => deleteHoursEntry(e.id)} style={styles.smBtn}>
                      <Feather name="trash-2" size={16} color={colors.alert} />
                    </TouchableOpacity>
                  </View>
                );
              })}
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* Hours Sheets — edit individual clock entry */}
      <Modal visible={!!hoursEditEntry} transparent animationType="slide" onRequestClose={() => setHoursEditEntry(null)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <Text style={typography.h3}>Edit clock entry</Text>
            <Text style={typography.label}>Clock in (YYYY-MM-DDTHH:MM)</Text>
            <TextInput
              style={styles.input}
              value={hoursEditEntry?.clock_in_iso || ""}
              onChangeText={(v) => setHoursEditEntry((p: any) => ({ ...p, clock_in_iso: v }))}
              placeholder="2026-05-22T08:00"
              placeholderTextColor={colors.textMuted}
            />
            <Text style={[typography.label, { marginTop: 8 }]}>Clock out (blank = still clocked in)</Text>
            <TextInput
              style={styles.input}
              value={hoursEditEntry?.clock_out_iso || ""}
              onChangeText={(v) => setHoursEditEntry((p: any) => ({ ...p, clock_out_iso: v }))}
              placeholder="2026-05-22T17:30"
              placeholderTextColor={colors.textMuted}
            />
            <Text style={[typography.label, { marginTop: 8 }]}>Note</Text>
            <TextInput
              style={[styles.input, { height: 64 }]}
              value={hoursEditEntry?.note || ""}
              onChangeText={(v) => setHoursEditEntry((p: any) => ({ ...p, note: v }))}
              multiline
            />
            <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
              <TouchableOpacity onPress={() => setHoursEditEntry(null)} style={[styles.modalBtn, { backgroundColor: colors.surface }]}>
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={saveHoursEntry} style={[styles.modalBtn, { backgroundColor: colors.primary }]}>
                <Text style={{ color: "#fff", fontWeight: "700" }}>Save</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </>
    );
  }
}

function formatBytesAdmin(n: number) {
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function DeskMetric({
  label,
  value,
  accent,
  icon,
}: {
  label: string;
  value: number;
  accent: string;
  icon: any;
}) {
  return (
    <View style={styles.deskMetricCard}>
      <View style={[styles.deskMetricIcon, { backgroundColor: `${accent}22` }]}>
        <Feather name={icon} size={18} color={accent} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[typography.small, { color: colors.textMuted, fontSize: 11, fontWeight: "600" }]}>
          {label.toUpperCase()}
        </Text>
        <Text style={{ color: colors.primary, fontSize: 24, fontWeight: "800", marginTop: 2 }}>
          {value}
        </Text>
      </View>
    </View>
  );
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

  // ===== A2: Forms Submissions Inbox =====
  formsSegmentRow: { flexDirection: "row", gap: 6, marginBottom: 12 },
  formsSegBtn: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    gap: 6,
  },
  formsSegBtnActive: { backgroundColor: colors.primary },
  formsSegBtnText: { fontWeight: "700", fontSize: 13, color: colors.primary },
  inboxFilterBar: {
    backgroundColor: "#F8FAFC",
    borderRadius: radius.lg,
    padding: 12,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: colors.border,
  },
  filterGroup: { flexShrink: 1 },
  filterLabel: {
    fontSize: 10,
    fontWeight: "700",
    color: colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginBottom: 4,
  },
  filterChip: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: colors.border,
  },
  filterChipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  filterChipText: { fontSize: 11, fontWeight: "600", color: colors.textSecondary },
  filterInput: {
    height: 36,
    backgroundColor: "#fff",
    borderRadius: radius.md,
    paddingHorizontal: 10,
    borderWidth: 1,
    borderColor: colors.border,
    fontSize: 13,
    color: colors.textPrimary,
  },
  reviewedToggle: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  reviewedToggleOn: { backgroundColor: "#0F766E", borderColor: "#0F766E" },
  reviewedToggleOff: { backgroundColor: "#fff", borderColor: colors.border },
  inboxCardUnreviewed: { borderLeftWidth: 3, borderLeftColor: colors.brand },

  // A4: Customer alphabetical section header
  azSectionHeader: {
    fontSize: 11,
    fontWeight: "800",
    color: colors.brand,
    backgroundColor: colors.brandSoft,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
    alignSelf: "flex-start",
    marginTop: 12,
    marginBottom: 4,
    letterSpacing: 1,
  },

  // ===== Desktop layout (Connecteam-style) =====
  deskRoot: { flex: 1, flexDirection: "row", backgroundColor: "#F6F8FB" },
  sidebar: {
    width: 240,
    backgroundColor: "#fff",
    paddingHorizontal: 14,
    paddingVertical: 18,
    borderRightWidth: 1,
    borderRightColor: colors.border,
  },
  sidebarCollapsed: {
    width: 64,
    paddingHorizontal: 8,
  },
  sidebarLogo: { flexDirection: "row", alignItems: "center", marginBottom: 24, paddingHorizontal: 4 },
  logoMark: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: colors.brand,
    alignItems: "center",
    justifyContent: "center",
  },
  logoText: { marginLeft: 10, fontWeight: "800", fontSize: 18, color: colors.primary },
  sidebarSection: {
    fontSize: 10,
    fontWeight: "700",
    color: colors.textMuted,
    letterSpacing: 1,
    marginTop: 14,
    marginBottom: 6,
    paddingHorizontal: 8,
  },
  sideNav: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10,
    paddingVertical: 10,
    borderRadius: 8,
    marginBottom: 2,
  },
  sideNavActive: { backgroundColor: colors.brandSoft },
  sideNavText: { marginLeft: 10, color: colors.textMuted, fontWeight: "600", fontSize: 13 },
  sideNavTextActive: { color: colors.brand },
  deskMain: { flex: 1, backgroundColor: "#F6F8FB" },
  deskTopbar: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 28,
    paddingVertical: 18,
    backgroundColor: "#fff",
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  adminBadge: { flexDirection: "row", alignItems: "center" },
  adminAvatar: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: colors.brand,
    alignItems: "center",
    justifyContent: "center",
  },
  deskMetrics: {
    flexDirection: "row",
    gap: 16,
    paddingHorizontal: 28,
    paddingTop: 20,
    paddingBottom: 4,
    flexWrap: "wrap",
  },
  deskMetricCard: {
    flex: 1,
    minWidth: 180,
    backgroundColor: "#fff",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: 16,
    paddingVertical: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  deskMetricIcon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  deskContent: { paddingHorizontal: 28, paddingTop: 20, paddingBottom: 40, gap: spacing.sm },

  // Drag-and-drop reassignment strip (desktop only)
  dropZoneStrip: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 8,
    backgroundColor: "#fff",
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: "dashed" as any,
    borderColor: colors.brand,
    marginTop: 8,
    marginBottom: 4,
  },
  dropChip: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brandSoft,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.brandSoft,
  },
  dropChipActive: {
    backgroundColor: colors.brand,
    borderColor: colors.brand,
  },
  desktopToggle: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: colors.brandSoft,
  },
  rosterPickBtn: {
    borderWidth: 1,
    borderStyle: "dashed" as any,
    borderColor: colors.brand,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    paddingVertical: 24,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 4,
  },
  rosterRow: {
    flexDirection: "row",
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    alignItems: "center",
  },
  rosterDayPill: {
    fontSize: 10,
    color: colors.primary,
    backgroundColor: colors.surface,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 999,
    overflow: "hidden",
  },
  userPick: {
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  templatesBar: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 6,
    backgroundColor: colors.brandSoft,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 8,
    marginTop: 6,
    marginBottom: 6,
  },
  templatePill: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#fff",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.brand,
  },
  savePillBtn: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brand,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 999,
    marginLeft: "auto",
  },
});


const hsStyles = StyleSheet.create({
  controls: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#fff",
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 10,
    marginBottom: 10,
  },
  weekNav: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
  },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: radius.pill,
  },
  summaryRow: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 12,
  },
  summaryCell: {
    flex: 1,
    backgroundColor: colors.surface,
    padding: 10,
    borderRadius: radius.md,
  },
  tableHeader: {
    flexDirection: "row",
    paddingHorizontal: 10,
    paddingVertical: 8,
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.md,
    borderTopRightRadius: radius.md,
    alignItems: "center",
  },
  thName: { flex: 2, fontSize: 11, fontWeight: "700", color: colors.textMuted, textTransform: "uppercase" },
  thDay: { width: 44, fontSize: 11, fontWeight: "700", color: colors.textMuted, textAlign: "center" },
  thTotal: { width: 60, fontSize: 11, fontWeight: "700", color: colors.textMuted, textAlign: "right" },
  row: {
    flexDirection: "row",
    paddingHorizontal: 10,
    paddingVertical: 12,
    backgroundColor: "#fff",
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    alignItems: "center",
  },
  tdName: { flex: 2, paddingRight: 6 },
  tdDay: { width: 44, fontSize: 13, color: colors.textMuted, textAlign: "center" },
  tdTotal: { width: 60, fontSize: 14, fontWeight: "700", color: colors.textPrimary, textAlign: "right" },
});
