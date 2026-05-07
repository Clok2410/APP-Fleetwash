import AsyncStorage from "@react-native-async-storage/async-storage";
import axios, { AxiosInstance } from "axios";

const BASE_URL = process.env.EXPO_PUBLIC_BACKEND_URL;

export const api: AxiosInstance = axios.create({
  baseURL: `${BASE_URL}/api`,
  timeout: 30000,
});

api.interceptors.request.use(async (config) => {
  const token = await AsyncStorage.getItem("access_token");
  if (token) {
    config.headers = config.headers || {};
    (config.headers as any).Authorization = `Bearer ${token}`;
  }
  return config;
});

export const setToken = async (token: string | null) => {
  if (token) await AsyncStorage.setItem("access_token", token);
  else await AsyncStorage.removeItem("access_token");
};

export const getToken = () => AsyncStorage.getItem("access_token");

export function formatApiError(detail: any): string {
  if (detail == null) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}
