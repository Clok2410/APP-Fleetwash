// Cross-platform helper to read a file picker asset as base64 (no data URL prefix).
// Robust on web (handles File/Blob, data: URL, blob: URL) and falls back to expo-file-system on native.
import { Platform } from "react-native";

function readBlobAsBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => {
      const result = fr.result as string;
      const idx = result.indexOf(",");
      resolve(idx >= 0 ? result.slice(idx + 1) : result);
    };
    fr.onerror = () => reject(fr.error || new Error("FileReader failed"));
    fr.readAsDataURL(blob);
  });
}

export async function readAssetAsBase64(file: any, FileSystem?: any): Promise<string> {
  if (Platform.OS === "web") {
    // 1) Picker provided File / Blob
    if (file?.file && typeof (file.file as Blob).arrayBuffer === "function") {
      try {
        return await readBlobAsBase64(file.file);
      } catch {}
    }
    // 2) Pre-encoded base64
    if (typeof file?.base64 === "string" && file.base64.length > 0) {
      return file.base64;
    }
    // 3) data: URL
    if (typeof file?.uri === "string" && file.uri.startsWith("data:")) {
      const idx = file.uri.indexOf(",");
      const meta = file.uri.slice(0, idx);
      const payload = file.uri.slice(idx + 1);
      if (meta.includes(";base64")) return payload;
      try {
        return btoa(decodeURIComponent(payload));
      } catch {
        return "";
      }
    }
    // 4) blob: URL or any other URL
    if (typeof file?.uri === "string") {
      try {
        const r = await fetch(file.uri);
        const blob = await r.blob();
        return await readBlobAsBase64(blob);
      } catch {}
    }
    return "";
  }
  // Native
  if (file?.base64) return file.base64;
  if (FileSystem?.readAsStringAsync) {
    try {
      return await FileSystem.readAsStringAsync(file.uri, {
        encoding: FileSystem.EncodingType.Base64,
      });
    } catch {}
  }
  return "";
}
