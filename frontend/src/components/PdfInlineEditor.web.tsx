// Web-only inline editor for AcroForm PDFs.
// Renders each PDF page via pdfjs onto a <canvas>, then overlays HTML inputs
// (text / checkbox / select) at the exact widget rectangles so users can fill
// the form in its original layout.
import React, { useEffect, useMemo, useRef, useState } from "react";

type Field = {
  name: string;
  type: "text" | "checkbox" | "radio" | "select";
  value?: string;
  options?: string[] | null;
  page?: number;
  rect?: number[];           // PDF rect [x1, y1, x2, y2] in PDF user space
  page_width?: number;
  page_height?: number;
};

type Props = {
  pdfBase64: string;
  fields: Field[];
  values: Record<string, any>;
  onChange: (name: string, value: any) => void;
  readOnly?: boolean;
};

// Decode base64 → Uint8Array
function b64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

const SCALE = 1.4; // rendering scale — bigger = sharper but heavier

export default function PdfInlineEditor({ pdfBase64, fields, values, onChange, readOnly }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [pages, setPages] = useState<
    { pageNumber: number; width: number; height: number; viewportWidth: number; viewportHeight: number }[]
  >([]);
  const [pdfReady, setPdfReady] = useState(false);
  const [error, setError] = useState<string>("");

  const bytes = useMemo(() => (pdfBase64 ? b64ToBytes(pdfBase64) : null), [pdfBase64]);

  useEffect(() => {
    if (!bytes) return;
    let cancelled = false;
    (async () => {
      try {
        // pdfjs-dist is web-only — dynamic import keeps native bundle clean.
        const pdfjs: any = await import("pdfjs-dist/build/pdf");
        // Use a CDN worker URL to avoid bundling the worker file ourselves.
        const versionedWorker = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.js`;
        pdfjs.GlobalWorkerOptions.workerSrc = versionedWorker;

        const loadingTask = pdfjs.getDocument({ data: bytes });
        const pdf = await loadingTask.promise;
        if (cancelled) return;

        // Clear container, render each page sequentially
        const container = containerRef.current;
        if (!container) return;
        container.innerHTML = "";
        const out: typeof pages = [];

        for (let i = 1; i <= pdf.numPages; i++) {
          const page = await pdf.getPage(i);
          const viewport = page.getViewport({ scale: SCALE });

          // Wrapper for canvas + absolute-positioned inputs
          const pageWrap = document.createElement("div");
          pageWrap.style.position = "relative";
          pageWrap.style.margin = "0 auto 16px";
          pageWrap.style.width = `${viewport.width}px`;
          pageWrap.style.height = `${viewport.height}px`;
          pageWrap.style.boxShadow = "0 1px 6px rgba(0,0,0,0.15)";
          pageWrap.style.background = "#fff";
          pageWrap.setAttribute("data-page", String(i));

          const canvas = document.createElement("canvas");
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          canvas.style.display = "block";
          canvas.style.width = `${viewport.width}px`;
          canvas.style.height = `${viewport.height}px`;
          pageWrap.appendChild(canvas);

          // Overlay container for inputs at original widget positions
          const overlay = document.createElement("div");
          overlay.setAttribute("data-overlay", String(i));
          overlay.style.position = "absolute";
          overlay.style.inset = "0";
          overlay.style.pointerEvents = "none"; // children re-enable
          pageWrap.appendChild(overlay);

          container.appendChild(pageWrap);

          const renderCtx = canvas.getContext("2d");
          if (!renderCtx) continue;
          await page.render({ canvasContext: renderCtx, viewport }).promise;

          out.push({
            pageNumber: i,
            width: viewport.width,
            height: viewport.height,
            viewportWidth: page.view[2] - page.view[0],
            viewportHeight: page.view[3] - page.view[1],
          });
        }

        if (!cancelled) {
          setPages(out);
          setPdfReady(true);
        }
      } catch (e: any) {
        if (!cancelled) setError(String(e?.message || e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [bytes]);

  // Mount inputs into the overlays whenever fields or values change
  useEffect(() => {
    if (!pdfReady) return;
    const container = containerRef.current;
    if (!container) return;

    const overlays = container.querySelectorAll<HTMLDivElement>("[data-overlay]");
    overlays.forEach((ov) => (ov.innerHTML = ""));

    for (const f of fields) {
      if (f.page == null || !f.rect) continue;
      const pageInfo = pages.find((p) => p.pageNumber === f.page! + 1);
      if (!pageInfo) continue;
      const overlay = container.querySelector<HTMLDivElement>(`[data-overlay="${f.page! + 1}"]`);
      if (!overlay) continue;

      const [x1, y1, x2, y2] = f.rect;
      const pdfW = f.page_width || pageInfo.viewportWidth || 612;
      const pdfH = f.page_height || pageInfo.viewportHeight || 792;
      const sx = pageInfo.width / pdfW;
      const sy = pageInfo.height / pdfH;
      const left = x1 * sx;
      const top = (pdfH - y2) * sy;
      const width = (x2 - x1) * sx;
      const height = (y2 - y1) * sy;

      let el: HTMLElement;
      if (f.type === "checkbox") {
        el = document.createElement("input");
        (el as HTMLInputElement).type = "checkbox";
        (el as HTMLInputElement).checked = !!values[f.name];
        el.style.width = `${Math.max(14, width)}px`;
        el.style.height = `${Math.max(14, height)}px`;
        (el as HTMLInputElement).disabled = !!readOnly;
        el.addEventListener("change", (e) => {
          onChange(f.name, (e.target as HTMLInputElement).checked);
        });
      } else if (f.type === "select" && f.options && f.options.length) {
        el = document.createElement("select");
        (el as HTMLSelectElement).disabled = !!readOnly;
        const opts = ["", ...f.options];
        for (const o of opts) {
          const optEl = document.createElement("option");
          optEl.value = o;
          optEl.textContent = o || "—";
          (el as HTMLSelectElement).appendChild(optEl);
        }
        (el as HTMLSelectElement).value = String(values[f.name] ?? "");
        el.style.width = `${width}px`;
        el.style.height = `${height}px`;
        el.style.fontSize = `${Math.max(10, Math.min(14, height * 0.55))}px`;
        el.addEventListener("change", (e) => {
          onChange(f.name, (e.target as HTMLSelectElement).value);
        });
      } else {
        // text (default)
        el = document.createElement("input");
        (el as HTMLInputElement).type = "text";
        (el as HTMLInputElement).value = String(values[f.name] ?? "");
        (el as HTMLInputElement).readOnly = !!readOnly;
        el.style.width = `${width}px`;
        el.style.height = `${height}px`;
        el.style.fontSize = `${Math.max(10, Math.min(14, height * 0.55))}px`;
        el.style.padding = "0 4px";
        el.style.boxSizing = "border-box";
        el.addEventListener("input", (e) => {
          onChange(f.name, (e.target as HTMLInputElement).value);
        });
      }
      el.style.position = "absolute";
      el.style.left = `${left}px`;
      el.style.top = `${top}px`;
      el.style.background = "rgba(255, 245, 157, 0.55)";
      el.style.border = "1px solid rgba(15, 23, 42, 0.45)";
      el.style.borderRadius = "2px";
      el.style.outline = "none";
      el.style.pointerEvents = "auto";
      el.title = f.name;
      el.setAttribute("data-field", f.name);
      overlay.appendChild(el);
    }
  }, [pdfReady, fields, values, pages, readOnly, onChange]);

  if (error) {
    return (
      <div style={{ padding: 12, color: "#B91C1C", background: "#FEE2E2", borderRadius: 8 }}>
        Couldn't render PDF: {error}
      </div>
    );
  }
  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        maxHeight: "70vh",
        overflow: "auto",
        background: "#0F172A",
        borderRadius: 8,
        padding: 8,
      }}
    />
  );
}
