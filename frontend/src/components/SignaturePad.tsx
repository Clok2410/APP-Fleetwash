// Native signature pad using react-native-signature-canvas (WebView based).
// Returns base64 PNG via onSave (no data: prefix in the produced string is fine — backend strips it).
import React, { useRef, useState } from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { Feather } from "@expo/vector-icons";
// @ts-ignore — types not bundled
import SignatureScreen from "react-native-signature-canvas";

type Props = {
  onSave: (base64DataUrl: string) => void;
  onCancel?: () => void;
  height?: number;
};

export default function SignaturePadNative({ onSave, onCancel, height = 220 }: Props) {
  const ref = useRef<any>(null);
  const [isEmpty, setIsEmpty] = useState(true);

  const handleOK = (signature: string) => {
    // signature is data:image/png;base64,<...>
    onSave(signature);
  };

  const handleClear = () => {
    ref.current?.clearSignature?.();
    setIsEmpty(true);
  };

  const handleConfirm = () => {
    ref.current?.readSignature?.();
  };

  const webStyle = `
    .m-signature-pad { box-shadow: none; border: none; }
    .m-signature-pad--body { border: 1px solid #E2E8F0; border-radius: 10px; }
    .m-signature-pad--footer { display: none; margin: 0; }
    body, html { background: #fff; }
  `;

  return (
    <View>
      <View style={[styles.pad, { height }]}>
        <SignatureScreen
          ref={ref}
          onOK={handleOK}
          onEmpty={() => setIsEmpty(true)}
          onBegin={() => setIsEmpty(false)}
          webStyle={webStyle}
          imageType="image/png"
          backgroundColor="rgba(255,255,255,1)"
          penColor="#0F172A"
        />
      </View>
      <Text style={styles.hint}>Sign above using your finger</Text>
      <View style={styles.btnRow}>
        {onCancel && (
          <TouchableOpacity testID="sig-cancel" onPress={onCancel} style={[styles.btn, styles.btnGhost]}>
            <Text style={styles.btnGhostText}>Cancel</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity testID="sig-clear" onPress={handleClear} style={[styles.btn, styles.btnGhost]}>
          <Feather name="rotate-ccw" size={13} color="#334155" />
          <Text style={[styles.btnGhostText, { marginLeft: 6 }]}>Clear</Text>
        </TouchableOpacity>
        <TouchableOpacity
          testID="sig-save"
          onPress={handleConfirm}
          disabled={isEmpty}
          style={[styles.btn, styles.btnPrimary, isEmpty && { opacity: 0.45 }]}
        >
          <Feather name="check" size={13} color="#fff" />
          <Text style={[styles.btnPrimaryText, { marginLeft: 6 }]}>Use signature</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  pad: {
    width: "100%",
    backgroundColor: "#fff",
    borderRadius: 10,
    overflow: "hidden",
  },
  hint: { fontSize: 11, color: "#64748B", marginTop: 6, textAlign: "center" },
  btnRow: { flexDirection: "row", gap: 8, marginTop: 10, justifyContent: "flex-end" },
  btn: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 14,
    height: 38,
    borderRadius: 999,
  },
  btnGhost: { backgroundColor: "#F1F5F9" },
  btnGhostText: { color: "#334155", fontWeight: "700", fontSize: 12 },
  btnPrimary: { backgroundColor: "#2563EB" },
  btnPrimaryText: { color: "#fff", fontWeight: "700", fontSize: 12 },
});
