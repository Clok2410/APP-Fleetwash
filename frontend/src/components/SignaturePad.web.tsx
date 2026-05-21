// Web (HTML5 canvas) signature pad. Returns base64 PNG via onSave.
// Compatible with React Native Web — uses raw <canvas> via createElement on web only.
import React, { useRef, useEffect, useCallback, useState } from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { Feather } from "@expo/vector-icons";

type Props = {
  onSave: (base64DataUrl: string) => void;
  onCancel?: () => void;
  height?: number;
};

export default function SignaturePadWeb({ onSave, onCancel, height = 220 }: Props) {
  const containerRef = useRef<View | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawingRef = useRef(false);
  const lastRef = useRef<{ x: number; y: number } | null>(null);
  const [isEmpty, setIsEmpty] = useState(true);

  const attachCanvas = useCallback((node: any) => {
    if (!node) return;
    // Find/create canvas inside the container
    let canvas = node.querySelector("canvas") as HTMLCanvasElement | null;
    if (!canvas) {
      canvas = document.createElement("canvas");
      canvas.style.width = "100%";
      canvas.style.height = "100%";
      canvas.style.touchAction = "none";
      canvas.style.cursor = "crosshair";
      canvas.style.borderRadius = "8px";
      canvas.style.background = "#fff";
      node.appendChild(canvas);
    }
    canvasRef.current = canvas;
    // Match canvas internal resolution to its CSS size for crisp lines
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.scale(dpr, dpr);
      ctx.lineWidth = 2.2;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.strokeStyle = "#0F172A";
    }
  }, []);

  const pointerPos = (e: PointerEvent) => {
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const onDown = (e: PointerEvent) => {
      e.preventDefault();
      drawingRef.current = true;
      lastRef.current = pointerPos(e);
      (canvas as any).setPointerCapture?.(e.pointerId);
    };
    const onMove = (e: PointerEvent) => {
      if (!drawingRef.current || !ctx) return;
      const p = pointerPos(e);
      const last = lastRef.current!;
      ctx.beginPath();
      ctx.moveTo(last.x, last.y);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
      lastRef.current = p;
      if (isEmpty) setIsEmpty(false);
    };
    const onUp = (e: PointerEvent) => {
      drawingRef.current = false;
      lastRef.current = null;
      (canvas as any).releasePointerCapture?.(e.pointerId);
    };
    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerup", onUp);
    canvas.addEventListener("pointercancel", onUp);
    canvas.addEventListener("pointerleave", onUp);
    return () => {
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("pointercancel", onUp);
      canvas.removeEventListener("pointerleave", onUp);
    };
  }, [isEmpty]);

  const clear = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx?.clearRect(0, 0, canvas.width, canvas.height);
    setIsEmpty(true);
  };

  const save = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    if (isEmpty) return;
    // Trim transparent edges + export as PNG dataURL
    const dataUrl = canvas.toDataURL("image/png");
    onSave(dataUrl);
  };

  return (
    <View>
      <View
        ref={(n: any) => { containerRef.current = n; attachCanvas(n); }}
        style={[styles.pad, { height }]}
      />
      <Text style={styles.hint}>Sign above using your mouse or finger</Text>
      <View style={styles.btnRow}>
        {onCancel && (
          <TouchableOpacity testID="sig-cancel" onPress={onCancel} style={[styles.btn, styles.btnGhost]}>
            <Text style={styles.btnGhostText}>Cancel</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity testID="sig-clear" onPress={clear} style={[styles.btn, styles.btnGhost]}>
          <Feather name="rotate-ccw" size={13} color="#334155" />
          <Text style={[styles.btnGhostText, { marginLeft: 6 }]}>Clear</Text>
        </TouchableOpacity>
        <TouchableOpacity
          testID="sig-save"
          onPress={save}
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
    borderWidth: 1,
    borderColor: "#E2E8F0",
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
