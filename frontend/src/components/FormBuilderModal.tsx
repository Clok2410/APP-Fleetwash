import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  Alert,
  Modal,
  StyleSheet,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { api } from "../api";
import { colors, spacing, radius, typography } from "../theme";

type Props = {
  visible: boolean;
  onClose: () => void;
  onPublished: () => void;
  depots?: { id: string; name: string }[];
};

export default function FormBuilderModal({ visible, onClose, onPublished, depots = [] }: Props) {
  const [fKind, setFKind] = useState<"form" | "checklist">("form");
  const [fTitle, setFTitle] = useState("");
  const [fDesc, setFDesc] = useState("");
  const [fTarget, setFTarget] = useState("100");
  const [fDepotId, setFDepotId] = useState<string>("");
  const [fields, setFields] = useState<any[]>([
    { key: "name", label: "Full Name", type: "text", required: true },
  ]);
  const [items, setItems] = useState<{ id: string; label: string; sub_keys: string[] }[]>([
    { id: "HL29", label: "HL 29", sub_keys: ["EXT", "INT"] },
    { id: "HL30", label: "HL 30", sub_keys: ["EXT", "INT"] },
  ]);
  const [subKeysInput, setSubKeysInput] = useState("EXT,INT");
  const [bulkInput, setBulkInput] = useState("");

  const reset = () => {
    setFKind("form");
    setFTitle("");
    setFDesc("");
    setFTarget("100");
    setFields([{ key: "name", label: "Full Name", type: "text", required: true }]);
    setItems([
      { id: "HL29", label: "HL 29", sub_keys: ["EXT", "INT"] },
      { id: "HL30", label: "HL 30", sub_keys: ["EXT", "INT"] },
    ]);
    setBulkInput("");
  };

  const create = async () => {
    if (!fTitle) return Alert.alert("Missing info", "Title required");
    if (fKind === "form" && fields.length === 0)
      return Alert.alert("Missing info", "Add at least one field");
    if (fKind === "checklist" && items.length === 0)
      return Alert.alert("Missing info", "Add at least one checklist item");
    try {
      await api.post("/forms/templates", {
        title: fTitle,
        description: fDesc,
        kind: fKind,
        fields: fKind === "form" ? fields : [],
        checklist_items: fKind === "checklist" ? items : [],
        target_percent: fKind === "checklist" ? parseFloat(fTarget) || 100 : null,
        depot_id: fKind === "checklist" && fDepotId ? fDepotId : null,
      });
      reset();
      onPublished();
      onClose();
      Alert.alert("Published", "Staff can now fill it out");
    } catch (e: any) {
      Alert.alert("Error", e.response?.data?.detail || "Failed");
    }
  };

  const bulkAdd = () => {
    const subs = subKeysInput.split(",").map((s) => s.trim()).filter(Boolean);
    if (subs.length === 0) return Alert.alert("Sub-tasks needed", "e.g. EXT,INT");
    const lines = bulkInput.split(/[\n,]/).map((s) => s.trim()).filter(Boolean);
    if (lines.length === 0) return Alert.alert("Add items", "Enter one item per line");
    setItems([
      ...items,
      ...lines.map((label) => ({
        id: label.replace(/\s+/g, "").toUpperCase(),
        label,
        sub_keys: subs,
      })),
    ]);
    setBulkInput("");
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={{ flex: 1, backgroundColor: "#fff" }}>
        <View style={s.header}>
          <TouchableOpacity onPress={onClose}>
            <Feather name="x" size={24} color={colors.primary} />
          </TouchableOpacity>
          <Text style={[typography.h3, { marginLeft: 12 }]}>New Template</Text>
        </View>
        <ScrollView contentContainerStyle={{ padding: spacing.lg }}>
          <View style={{ flexDirection: "row", gap: 8, marginBottom: 12 }}>
            {(["form", "checklist"] as const).map((k) => (
              <TouchableOpacity
                key={k}
                testID={`kind-${k}`}
                style={[s.chip, fKind === k && { backgroundColor: colors.primary }]}
                onPress={() => setFKind(k)}
              >
                <Text style={{ color: fKind === k ? "#fff" : colors.primary, fontWeight: "700" }}>
                  {k === "form" ? "Form" : "Checklist"}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          <TextInput
            style={s.input}
            placeholder="Title (e.g. Daily Truck Wash)"
            value={fTitle}
            onChangeText={setFTitle}
            placeholderTextColor={colors.textMuted}
          />
          <TextInput
            style={[s.input, { height: 70 }]}
            placeholder="Description"
            value={fDesc}
            onChangeText={setFDesc}
            multiline
            placeholderTextColor={colors.textMuted}
          />

          {fKind === "form" ? (
            <>
              <Text style={[typography.label, { marginTop: 16 }]}>Fields</Text>
              {fields.map((f, idx) => (
                <View key={idx} style={s.fieldEditor}>
                  <TextInput
                    style={[s.input, { flex: 1 }]}
                    placeholder="Label"
                    value={f.label}
                    onChangeText={(v) => {
                      const c = [...fields];
                      c[idx].label = v;
                      c[idx].key = v.toLowerCase().replace(/\s+/g, "_") || `f${idx}`;
                      setFields(c);
                    }}
                  />
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 4, marginTop: 6 }}>
                    {["text", "textarea", "date", "checkbox", "signature", "select", "number"].map((t) => (
                      <TouchableOpacity
                        key={t}
                        onPress={() => {
                          const c = [...fields];
                          c[idx].type = t;
                          setFields(c);
                        }}
                        style={[s.chip, f.type === t && { backgroundColor: colors.primary }]}
                      >
                        <Text style={{ color: f.type === t ? "#fff" : colors.primary, fontSize: 11, fontWeight: "600" }}>
                          {t}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                  <TouchableOpacity
                    onPress={() => setFields(fields.filter((_, i) => i !== idx))}
                    style={{ alignSelf: "flex-end", marginTop: 4 }}
                  >
                    <Text style={{ color: colors.alert, fontSize: 12, fontWeight: "700" }}>REMOVE</Text>
                  </TouchableOpacity>
                </View>
              ))}
              <TouchableOpacity
                style={[s.btn, { backgroundColor: colors.surface, marginTop: 8 }]}
                onPress={() =>
                  setFields([
                    ...fields,
                    { key: `f${fields.length}`, label: "New Field", type: "text", required: false },
                  ])
                }
              >
                <Text style={{ color: colors.primary, fontWeight: "700" }}>+ Add Field</Text>
              </TouchableOpacity>
            </>
          ) : (
            <>
              <Text style={[typography.label, { marginTop: 16 }]}>Sub-tasks per item (comma separated)</Text>
              <TextInput
                testID="checklist-subkeys"
                style={s.input}
                placeholder="EXT,INT"
                value={subKeysInput}
                onChangeText={setSubKeysInput}
                placeholderTextColor={colors.textMuted}
              />
              <Text style={[typography.label, { marginTop: 16 }]}>Target % (e.g. 100)</Text>
              <TextInput
                testID="checklist-target"
                style={s.input}
                placeholder="100"
                value={fTarget}
                onChangeText={setFTarget}
                keyboardType="numeric"
                placeholderTextColor={colors.textMuted}
              />

              {depots.length > 0 && (
                <>
                  <Text style={[typography.label, { marginTop: 16 }]}>Depot (optional)</Text>
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                    <TouchableOpacity
                      testID="depot-pick-none"
                      onPress={() => setFDepotId("")}
                      style={[s.chip, !fDepotId && { backgroundColor: colors.primary }]}
                    >
                      <Text style={{ color: !fDepotId ? "#fff" : colors.primary, fontWeight: "600", fontSize: 12 }}>
                        None
                      </Text>
                    </TouchableOpacity>
                    {depots.map((d) => (
                      <TouchableOpacity
                        key={d.id}
                        testID={`depot-pick-${d.id}`}
                        onPress={() => setFDepotId(d.id)}
                        style={[s.chip, fDepotId === d.id && { backgroundColor: colors.primary }]}
                      >
                        <Text
                          style={{ color: fDepotId === d.id ? "#fff" : colors.primary, fontWeight: "600", fontSize: 12 }}
                        >
                          {d.name}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </>
              )}

              <Text style={[typography.label, { marginTop: 16 }]}>Items ({items.length})</Text>
              {items.map((it, idx) => (
                <View key={idx} style={[s.fieldEditor, { flexDirection: "row", alignItems: "center", gap: 8 }]}>
                  <TextInput
                    style={[s.input, { flex: 1, marginTop: 0 }]}
                    placeholder="Label (e.g. HL 29)"
                    value={it.label}
                    onChangeText={(v) => {
                      const c = [...items];
                      c[idx] = { ...c[idx], label: v, id: v.replace(/\s+/g, "").toUpperCase() || `IT${idx}` };
                      setItems(c);
                    }}
                  />
                  <TouchableOpacity onPress={() => setItems(items.filter((_, i) => i !== idx))}>
                    <Feather name="trash-2" size={16} color={colors.alert} />
                  </TouchableOpacity>
                </View>
              ))}
              <TouchableOpacity
                style={[s.btn, { backgroundColor: colors.surface, marginTop: 8 }]}
                onPress={() => {
                  const subs = subKeysInput.split(",").map((x) => x.trim()).filter(Boolean);
                  setItems([
                    ...items,
                    {
                      id: `IT${items.length}`,
                      label: `Item ${items.length + 1}`,
                      sub_keys: subs.length ? subs : ["EXT", "INT"],
                    },
                  ]);
                }}
              >
                <Text style={{ color: colors.primary, fontWeight: "700" }}>+ Add Single Item</Text>
              </TouchableOpacity>

              <Text style={[typography.label, { marginTop: 16 }]}>Bulk add (one item per line)</Text>
              <TextInput
                testID="checklist-bulk"
                style={[s.input, { height: 100, textAlignVertical: "top", paddingTop: 10 }]}
                multiline
                placeholder={"HL 29\nHL 30\nHL 31"}
                value={bulkInput}
                onChangeText={setBulkInput}
                placeholderTextColor={colors.textMuted}
              />
              <TouchableOpacity
                testID="checklist-bulk-add"
                style={[s.btn, { backgroundColor: colors.surface, marginTop: 8 }]}
                onPress={bulkAdd}
              >
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Append items</Text>
              </TouchableOpacity>
            </>
          )}

          <TouchableOpacity
            testID="publish-template"
            style={[s.btn, { backgroundColor: colors.primary, marginTop: 16 }]}
            onPress={create}
          >
            <Text style={{ color: "#fff", fontWeight: "700" }}>Publish</Text>
          </TouchableOpacity>
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
  chip: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
  },
  input: {
    height: 48,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    marginTop: spacing.sm,
    color: colors.textPrimary,
  },
  btn: { height: 48, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  fieldEditor: { backgroundColor: colors.surface, borderRadius: radius.md, padding: 10, marginTop: 6 },
});
