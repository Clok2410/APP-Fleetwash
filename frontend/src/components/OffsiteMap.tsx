import React from "react";
import { View, Text, StyleSheet, Platform } from "react-native";
import { colors, spacing, radius, typography } from "../theme";

type Entry = {
  id: string;
  user_name: string;
  lat?: number | null;
  lng?: number | null;
  depot_name?: string | null;
  distance_m?: number | null;
};

type Props = { entries: Entry[]; depots: { id: string; name: string; lat: number; lng: number; radius_m: number }[] };

export default function OffsiteMap({ entries, depots }: Props) {
  if (Platform.OS === "web") {
    return (
      <View style={s.webFallback}>
        <Text style={[typography.label, { color: colors.textSecondary }]}>Map preview</Text>
        <Text style={[typography.small, { marginTop: 4 }]}>
          Native map renders on iOS/Android. Tap any row's "Map" button to open the location in
          Google/Apple Maps.
        </Text>
        <Text style={[typography.small, { marginTop: 6, color: colors.textMuted }]}>
          {entries.length} pin{entries.length === 1 ? "" : "s"} · {depots.length} depot
          {depots.length === 1 ? "" : "s"}
        </Text>
      </View>
    );
  }

  // Lazy-require so web bundler never tries to resolve the native module.
  const Maps = require("react-native-maps");
  const MapView = Maps.default;
  const { Marker, Circle } = Maps;

  const points = entries.filter((e) => e.lat != null && e.lng != null);
  const initial =
    points[0]
      ? { latitude: points[0].lat as number, longitude: points[0].lng as number, latitudeDelta: 0.5, longitudeDelta: 0.5 }
      : depots[0]
      ? { latitude: depots[0].lat, longitude: depots[0].lng, latitudeDelta: 0.5, longitudeDelta: 0.5 }
      : { latitude: 53.3498, longitude: -6.2603, latitudeDelta: 50, longitudeDelta: 50 };

  return (
    <View style={s.mapWrap}>
      <MapView style={s.map} initialRegion={initial}>
        {depots.map((d) => (
          <React.Fragment key={d.id}>
            <Marker
              coordinate={{ latitude: d.lat, longitude: d.lng }}
              title={d.name}
              description={`${d.radius_m}m radius`}
              pinColor="green"
            />
            <Circle
              center={{ latitude: d.lat, longitude: d.lng }}
              radius={d.radius_m}
              strokeColor="rgba(16,185,129,0.6)"
              fillColor="rgba(16,185,129,0.1)"
            />
          </React.Fragment>
        ))}
        {points.map((e) => (
          <Marker
            key={e.id}
            coordinate={{ latitude: e.lat as number, longitude: e.lng as number }}
            title={e.user_name}
            description={`${Math.round(e.distance_m || 0)}m from ${e.depot_name || "depot"}`}
            pinColor="red"
          />
        ))}
      </MapView>
    </View>
  );
}

const s = StyleSheet.create({
  mapWrap: {
    height: 280,
    borderRadius: radius.lg,
    overflow: "hidden",
    marginBottom: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
  },
  map: { flex: 1 },
  webFallback: {
    padding: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.sm,
  },
});
