import React, { useEffect, useRef, useState } from "react";
import { View, ViewStyle } from "react-native";

type Props = {
  onFile: (file: File) => void;
  style?: ViewStyle;
  children?: React.ReactNode;
};

// Web: real HTML5 drag-and-drop using a wrapping <div> with a file input fallback.
export default function WebDropZone({ onFile, style, children }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [over, setOver] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const stop = (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
    };
    const onEnter = (e: DragEvent) => {
      stop(e);
      setOver(true);
    };
    const onLeave = (e: DragEvent) => {
      stop(e);
      setOver(false);
    };
    const onOver = (e: DragEvent) => {
      stop(e);
      setOver(true);
    };
    const onDrop = (e: DragEvent) => {
      stop(e);
      setOver(false);
      const f = e.dataTransfer?.files?.[0];
      if (f) onFile(f);
    };
    el.addEventListener("dragenter", onEnter);
    el.addEventListener("dragleave", onLeave);
    el.addEventListener("dragover", onOver);
    el.addEventListener("drop", onDrop);
    return () => {
      el.removeEventListener("dragenter", onEnter);
      el.removeEventListener("dragleave", onLeave);
      el.removeEventListener("dragover", onOver);
      el.removeEventListener("drop", onDrop);
    };
  }, [onFile]);

  // Render a real div so DOM events work; pass style through.
  const cssStyle: any = {
    ...(style as any),
    transition: "background 120ms",
    background: over ? "rgba(15, 23, 42, 0.06)" : "transparent",
    border: over ? "2px dashed #0F172A" : "2px dashed rgba(15, 23, 42, 0.25)",
    borderRadius: 12,
    padding: 16,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "column",
  };

  return (
    <div ref={ref} style={cssStyle}>
      {children}
    </div>
  );
}
