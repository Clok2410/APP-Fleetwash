import React, { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  Modal,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  TextInput,
  Alert,
  Linking,
  Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { api } from "../api";
import { useAuth } from "../auth";
import { colors, spacing, radius, typography } from "../theme";

const CATEGORIES = ["general", "access", "hazard", "equipment", "other"] as const;
const CATEGORY_COLORS: Record<string, string> = {
  general: "#94A3B8",
  access: "#0EA5E9",
  hazard: "#EF4444",
  equipment: "#F59E0B",
  other: "#A78BFA",
};

type Props = { customerId: string | null; onClose: () => void };

export default function CustomerModal({ customerId, onClose }: Props) {
  const { user } = useAuth();
  const [customer, setCustomer] = useState<any>(null);
  const [notes, setNotes] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [body, setBody] = useState("");
  const [cat, setCat] = useState<typeof CATEGORIES[number]>("general");
  const [pinned, setPinned] = useState(false);

  // Admin add-contact / add-site state
  const [addCName, setAddCName] = useState("");
  const [addCRole, setAddCRole] = useState("");
  const [addCPhone, setAddCPhone] = useState("");
  const [addCEmail, setAddCEmail] = useState("");

  const [addSName, setAddSName] = useState("");
  const [addSAddr, setAddSAddr] = useState("");
  const [addSDesc, setAddSDesc] = useState("");

  const load = useCallback(async () => {
    if (!customerId) return;
    setBusy(true);
    try {
      const [c, n] = await Promise.all([
        api.get(`/customers/${customerId}`),
        api.get(`/customers/${customerId}/notes`),
      ]);
      setCustomer(c.data);
      setNotes(n.data);
    } catch {} finally {
      setBusy(false);
    }
  }, [customerId]);

  useEffect(() => {
    if (customerId) load();
  }, [customerId, load]);

  const addNote = async () => {
    if (!body.trim()) return Alert.alert("Empty note");
    try {
      await api.post(`/customers/${customerId}/notes`, { body, category: cat, pinned });
      setBody("");
      setPinned(false);
      setCat("general");
      await load();
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Failed");
    }
  };

  const togglePin = async (n: any) => {
    try {
      await api.patch(`/customers/${customerId}/notes/${n.id}`, {
        body: n.body,
        category: n.category,
        pinned: !n.pinned,
      });
      await load();
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Failed");
    }
  };

  const deleteNote = async (n: any) => {
    try {
      await api.delete(`/customers/${customerId}/notes/${n.id}`);
      await load();
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Failed");
    }
  };

  const addContact = async () => {
    if (!addCName) return Alert.alert("Name required");
    await api.post(`/customers/${customerId}/contacts`, {
      name: addCName, role: addCRole, phone: addCPhone, email: addCEmail,
    });
    setAddCName(""); setAddCRole(""); setAddCPhone(""); setAddCEmail("");
    await load();
  };

  const removeContact = async (id: string) => {
    await api.delete(`/customers/${customerId}/contacts/${id}`);
    await load();
  };

  const addSite = async () => {
    if (!addSName) return Alert.alert("Name required");
    await api.post(`/customers/${customerId}/sites`, {
      name: addSName, address: addSAddr, description: addSDesc,
    });
    setAddSName(""); setAddSAddr(""); setAddSDesc("");
    await load();
  };

  const removeSite = async (id: string) => {
    await api.delete(`/customers/${customerId}/sites/${id}`);
    await load();
  };

  const dialOrEmail = (kind: "tel" | "mailto", value?: string) => {
    if (!value) return;
    Linking.openURL(`${kind}:${value}`);
  };

  const isAdmin = user?.role === "admin";

  return (
    <Modal visible={!!customerId} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={{ flex: 1, backgroundColor: "#fff" }}>
        <View style={s.header}>
          <TouchableOpacity onPress={onClose}><Feather name="x" size={24} color={colors.primary} /></TouchableOpacity>
          <Text style={[typography.h3, { marginLeft: 12, flex: 1 }]} numberOfLines={1}>
            {customer?.name || "Customer"}
          </Text>
        </View>

        {busy ? (
          <ActivityIndicator color={colors.brand} style={{ marginTop: 30 }} />
        ) : customer ? (
          <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}>
            <View style={s.card}>
              <Text style={typography.label}>Profile</Text>
              {customer.company ? <Text style={{ marginTop: 4, fontWeight: "600" }}>{customer.company}</Text> : null}
              {customer.email ? (
                <TouchableOpacity onPress={() => dialOrEmail("mailto", customer.email)}>
                  <Text style={[typography.small, { color: colors.brand, marginTop: 4 }]}>{customer.email}</Text>
                </TouchableOpacity>
              ) : null}
              {customer.phone ? (
                <TouchableOpacity onPress={() => dialOrEmail("tel", customer.phone)}>
                  <Text style={[typography.small, { color: colors.brand, marginTop: 2 }]}>{customer.phone}</Text>
                </TouchableOpacity>
              ) : null}
            </View>

            <View style={s.card}>
              <Text style={typography.label}>Site Contacts ({customer.contacts?.length || 0})</Text>
              {(customer.contacts || []).map((c: any) => (
                <View key={c.id} style={s.row} testID={`contact-${c.id}`}>
                  <View style={[s.iconBubble, { backgroundColor: colors.brandSoft }]}>
                    <Feather name="user" size={14} color={colors.brand} />
                  </View>
                  <View style={{ flex: 1, marginLeft: 8 }}>
                    <Text style={{ fontWeight: "700" }}>{c.name}{c.role ? ` · ${c.role}` : ""}</Text>
                    {c.phone ? (
                      <TouchableOpacity onPress={() => dialOrEmail("tel", c.phone)}>
                        <Text style={[typography.small, { color: colors.brand }]}>{c.phone}</Text>
                      </TouchableOpacity>
                    ) : null}
                    {c.email ? (
                      <TouchableOpacity onPress={() => dialOrEmail("mailto", c.email)}>
                        <Text style={[typography.small, { color: colors.brand }]}>{c.email}</Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                  {isAdmin && (
                    <TouchableOpacity onPress={() => removeContact(c.id)}>
                      <Feather name="trash-2" size={14} color={colors.alert} />
                    </TouchableOpacity>
                  )}
                </View>
              ))}
              {isAdmin && (
                <View style={{ marginTop: 8, gap: 4 }}>
                  <TextInput testID="add-contact-name" style={s.input} placeholder="Name" value={addCName} onChangeText={setAddCName} placeholderTextColor={colors.textMuted} />
                  <TextInput style={s.input} placeholder="Role" value={addCRole} onChangeText={setAddCRole} placeholderTextColor={colors.textMuted} />
                  <TextInput style={s.input} placeholder="Phone" value={addCPhone} onChangeText={setAddCPhone} placeholderTextColor={colors.textMuted} />
                  <TextInput style={s.input} placeholder="Email" value={addCEmail} onChangeText={setAddCEmail} autoCapitalize="none" placeholderTextColor={colors.textMuted} />
                  <TouchableOpacity testID="add-contact-submit" style={s.btnGhost} onPress={addContact}>
                    <Text style={s.btnGhostText}>+ Add Contact</Text>
                  </TouchableOpacity>
                </View>
              )}
            </View>

            <View style={s.card}>
              <Text style={typography.label}>Locations ({customer.sites?.length || 0})</Text>
              {(customer.sites || []).map((st: any) => (
                <View key={st.id} style={s.row} testID={`site-${st.id}`}>
                  <View style={[s.iconBubble, { backgroundColor: "#FEF3C7" }]}>
                    <Feather name="map-pin" size={14} color="#F59E0B" />
                  </View>
                  <View style={{ flex: 1, marginLeft: 8 }}>
                    <Text style={{ fontWeight: "700" }}>{st.name}</Text>
                    {st.address ? <Text style={typography.small}>{st.address}</Text> : null}
                    {st.description ? <Text style={typography.small}>{st.description}</Text> : null}
                  </View>
                  {isAdmin && (
                    <TouchableOpacity onPress={() => removeSite(st.id)}>
                      <Feather name="trash-2" size={14} color={colors.alert} />
                    </TouchableOpacity>
                  )}
                </View>
              ))}
              {isAdmin && (
                <View style={{ marginTop: 8, gap: 4 }}>
                  <TextInput testID="add-site-name" style={s.input} placeholder="Site name" value={addSName} onChangeText={setAddSName} placeholderTextColor={colors.textMuted} />
                  <TextInput style={s.input} placeholder="Address" value={addSAddr} onChangeText={setAddSAddr} placeholderTextColor={colors.textMuted} />
                  <TextInput style={s.input} placeholder="Notes / description" value={addSDesc} onChangeText={setAddSDesc} placeholderTextColor={colors.textMuted} />
                  <TouchableOpacity testID="add-site-submit" style={s.btnGhost} onPress={addSite}>
                    <Text style={s.btnGhostText}>+ Add Location</Text>
                  </TouchableOpacity>
                </View>
              )}
            </View>

            <View style={s.card}>
              <Text style={typography.label}>Crew Notes ({notes.length})</Text>
              <TextInput
                testID="note-body"
                style={[s.input, { height: 70, textAlignVertical: "top", paddingTop: 8 }]}
                multiline
                placeholder="Add a note for the crew…"
                value={body}
                onChangeText={setBody}
                placeholderTextColor={colors.textMuted}
              />
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 4, marginTop: 6 }}>
                {CATEGORIES.map((c) => (
                  <TouchableOpacity
                    key={c}
                    testID={`cat-${c}`}
                    onPress={() => setCat(c)}
                    style={[s.chip, cat === c && { backgroundColor: CATEGORY_COLORS[c] }]}
                  >
                    <Text style={{ color: cat === c ? "#fff" : colors.primary, fontSize: 11, fontWeight: "700" }}>{c}</Text>
                  </TouchableOpacity>
                ))}
                <TouchableOpacity
                  testID="note-pin-toggle"
                  onPress={() => setPinned(!pinned)}
                  style={[s.chip, pinned && { backgroundColor: colors.primary }]}
                >
                  <Feather name="bookmark" size={11} color={pinned ? "#fff" : colors.primary} />
                  <Text style={{ marginLeft: 4, color: pinned ? "#fff" : colors.primary, fontSize: 11, fontWeight: "700" }}>
                    pinned
                  </Text>
                </TouchableOpacity>
              </View>
              <TouchableOpacity testID="note-submit" style={[s.btnPrimary, { marginTop: 8 }]} onPress={addNote}>
                <Text style={{ color: "#fff", fontWeight: "700" }}>Post Note</Text>
              </TouchableOpacity>

              <View style={{ marginTop: 12, gap: 8 }}>
                {notes.map((n) => (
                  <View
                    key={n.id}
                    testID={`note-${n.id}`}
                    style={[
                      s.note,
                      n.pinned && { borderLeftWidth: 3, borderLeftColor: colors.primary, backgroundColor: "#FEFCE8" },
                    ]}
                  >
                    <View style={{ flexDirection: "row", alignItems: "center" }}>
                      <View style={[s.catPill, { backgroundColor: CATEGORY_COLORS[n.category] || "#94A3B8" }]}>
                        <Text style={{ color: "#fff", fontSize: 10, fontWeight: "700", textTransform: "uppercase" }}>
                          {n.category}
                        </Text>
                      </View>
                      {n.pinned && <Feather name="bookmark" size={12} color={colors.primary} style={{ marginLeft: 6 }} />}
                      <Text style={[typography.small, { marginLeft: "auto", color: colors.textMuted }]}>
                        {n.author_name} · {new Date(n.created_at).toLocaleDateString()}
                      </Text>
                    </View>
                    <Text style={{ marginTop: 6 }}>{n.body}</Text>
                    {(isAdmin || n.author_id === user?.id) && (
                      <View style={{ flexDirection: "row", gap: 12, marginTop: 6 }}>
                        <TouchableOpacity onPress={() => togglePin(n)}>
                          <Text style={{ fontSize: 12, color: colors.brand, fontWeight: "700" }}>
                            {n.pinned ? "Unpin" : "Pin"}
                          </Text>
                        </TouchableOpacity>
                        <TouchableOpacity onPress={() => deleteNote(n)}>
                          <Text style={{ fontSize: 12, color: colors.alert, fontWeight: "700" }}>Delete</Text>
                        </TouchableOpacity>
                      </View>
                    )}
                  </View>
                ))}
              </View>
            </View>
          </ScrollView>
        ) : null}
      </SafeAreaView>
    </Modal>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", padding: spacing.md, borderBottomColor: colors.border, borderBottomWidth: 1 },
  card: { backgroundColor: "#fff", borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.md },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 8, borderTopColor: colors.border, borderTopWidth: 1 },
  iconBubble: { width: 28, height: 28, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  input: { height: 40, backgroundColor: colors.surface, borderRadius: radius.md, paddingHorizontal: 10, marginTop: 4 },
  btnPrimary: { height: 44, borderRadius: radius.pill, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  btnGhost: { height: 40, borderRadius: radius.pill, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", marginTop: 4 },
  btnGhostText: { color: colors.primary, fontWeight: "700" },
  chip: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: colors.surface, flexDirection: "row", alignItems: "center" },
  note: { backgroundColor: "#fff", borderRadius: radius.md, padding: 10, borderWidth: 1, borderColor: colors.border },
  catPill: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
});
