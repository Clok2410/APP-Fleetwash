import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors, spacing, radius, typography } from "../theme";

type Entry = {
  id: string;
  user_name: string;
  lat?: number | null;
  lng?: number | null;
  depot_name?: string | null;
  distance_m?: number | null;
};

type Site = {
  id: string;
  name: string;
  lat: number;
  lng: number;
  radius_m?: number;
  customer_name?: string;
};

type Props = {
  entries: Entry[];
  depots: { id: string; name: string; lat: number; lng: number; radius_m: number }[];
  sites?: Site[];
};

export default function OffsiteMap({ entries, depots, sites = [] }: Props) {
  return (
    <View style={s.webFallback}>
      <Text style={[typography.label, { color: colors.textSecondary }]}>Map preview</Text>
      <Text style={[typography.small, { marginTop: 4 }]}>
        Native map renders on iOS/Android. Tap any row's "Map" button to open the location in
        Google/Apple Maps.
      </Text>
      <Text style={[typography.small, { marginTop: 6, color: colors.textMuted }]}>
        {entries.length} pin{entries.length === 1 ? "" : "s"} · {depots.length} depot
        {depots.length === 1 ? "" : "s"} · {sites.length} customer site{sites.length === 1 ? "" : "s"}
      </Text>
    </View>
  );
}

const s = StyleSheet.create({
  webFallback: {
    padding: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.sm,
  },
});
