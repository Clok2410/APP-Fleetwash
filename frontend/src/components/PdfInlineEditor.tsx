// Native fallback for the inline PDF editor. Real implementation lives in
// PdfInlineEditor.web.tsx. On native we just render nothing so the parent
// component falls back to its field-list editor.
import React from "react";

type Field = {
  name: string;
  type: "text" | "checkbox" | "radio" | "select";
  value?: string;
  options?: string[] | null;
  page?: number;
  rect?: number[];
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

export default function PdfInlineEditor(_props: Props) {
  return null;
}
