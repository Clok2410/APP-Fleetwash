import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Alert,
} from "react-native";
import { Redirect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useAuth } from "../src/auth";
import { colors, spacing, radius, typography } from "../src/theme";

export default function LoginScreen() {
  const { user, login } = useAuth();
  const [email, setEmail] = useState("admin@company.com");
  const [password, setPassword] = useState("Admin@123");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (user === undefined) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.brand} />
      </View>
    );
  }
  if (user) return <Redirect href="/(tabs)/home" />;

  const handleLogin = async () => {
    setErr(null);
    setBusy(true);
    try {
      await login(email.trim(), password);
    } catch (e: any) {
      setErr(e.message || "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={styles.container}
    >
      <View style={styles.brandBlock}>
        <View style={styles.logoMark}>
          <Feather name="zap" size={28} color="#fff" />
        </View>
        <Text style={typography.label}>Workforce OS</Text>
        <Text style={[typography.h1, { marginTop: 4 }]}>Fleetwash Hub.</Text>
        <Text style={[typography.body, { marginTop: 8 }]}>
          Clock in, manage shifts, share files, and complete forms — all in one place.
        </Text>
      </View>

      <View style={styles.formCard}>
        <Text style={typography.label}>Email</Text>
        <TextInput
          testID="login-email"
          style={styles.input}
          autoCapitalize="none"
          keyboardType="email-address"
          value={email}
          onChangeText={setEmail}
          placeholder="you@company.com"
          placeholderTextColor={colors.textMuted}
        />
        <View style={{ height: spacing.md }} />
        <Text style={typography.label}>Password</Text>
        <TextInput
          testID="login-password"
          style={styles.input}
          secureTextEntry
          value={password}
          onChangeText={setPassword}
          placeholder="••••••••"
          placeholderTextColor={colors.textMuted}
        />

        {err && (
          <Text testID="login-error" style={styles.error}>
            {err}
          </Text>
        )}

        <TouchableOpacity
          testID="login-submit"
          style={[styles.cta, busy && { opacity: 0.7 }]}
          activeOpacity={0.9}
          disabled={busy}
          onPress={handleLogin}
        >
          {busy ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.ctaText}>Sign in →</Text>
          )}
        </TouchableOpacity>

        <View style={styles.hintBox}>
          <Text style={typography.small}>Demo accounts:</Text>
          <Text style={[typography.small, { fontWeight: "600", color: colors.textPrimary }]}>
            admin@company.com / Admin@123
          </Text>
          <Text style={[typography.small, { fontWeight: "600", color: colors.textPrimary }]}>
            jane@company.com / Staff@123
          </Text>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background, padding: spacing.lg, justifyContent: "center" },
  center: { flex: 1, justifyContent: "center", alignItems: "center", backgroundColor: colors.background },
  brandBlock: { marginBottom: spacing.xl },
  logoMark: {
    width: 56,
    height: 56,
    borderRadius: radius.lg,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.md,
  },
  formCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.xl,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  input: {
    height: 52,
    backgroundColor: "#fff",
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    fontSize: 16,
    color: colors.textPrimary,
    marginTop: spacing.xs,
  },
  cta: {
    marginTop: spacing.lg,
    height: 56,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  ctaText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  error: { color: colors.alert, marginTop: spacing.sm, fontSize: 14 },
  hintBox: {
    marginTop: spacing.lg,
    padding: spacing.md,
    backgroundColor: colors.brandSoft,
    borderRadius: radius.md,
    gap: 2,
  },
});
