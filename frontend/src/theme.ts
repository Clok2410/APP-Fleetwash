export const colors = {
  background: "#FFFFFF",
  surface: "#F4F4F5",
  surfaceSecondary: "#E4E4E7",
  primary: "#0A0A0A",
  primaryFg: "#FFFFFF",
  brand: "#4338CA",
  brandSoft: "#EEF2FF",
  success: "#10B981",
  alert: "#EF4444",
  warning: "#F59E0B",
  textPrimary: "#0A0A0A",
  textSecondary: "#52525B",
  textMuted: "#A1A1AA",
  border: "#E4E4E7",
};

export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48 };
export const radius = { sm: 8, md: 12, lg: 16, xl: 24, pill: 9999 };

export const typography = {
  h1: { fontSize: 30, fontWeight: "700" as const, color: colors.textPrimary, letterSpacing: -0.5 },
  h2: { fontSize: 24, fontWeight: "700" as const, color: colors.textPrimary, letterSpacing: -0.3 },
  h3: { fontSize: 18, fontWeight: "600" as const, color: colors.textPrimary },
  body: { fontSize: 15, fontWeight: "500" as const, color: colors.textSecondary, lineHeight: 22 },
  label: {
    fontSize: 11,
    fontWeight: "700" as const,
    color: colors.textSecondary,
    letterSpacing: 2,
    textTransform: "uppercase" as const,
  },
  small: { fontSize: 13, color: colors.textSecondary },
};
