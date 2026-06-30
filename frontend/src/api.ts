import AsyncStorage from "@react-native-async-storage/async-storage";
import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from "axios";

const BASE_URL = process.env.EXPO_PUBLIC_BACKEND_URL;

const ACCESS_KEY = "access_token";
const REFRESH_KEY = "refresh_token";

export const api: AxiosInstance = axios.create({
  baseURL: `${BASE_URL}/api`,
  timeout: 30000,
});

// ---------- Request interceptor: attach access token ----------
api.interceptors.request.use(async (config) => {
  const token = await AsyncStorage.getItem(ACCESS_KEY);
  if (token) {
    config.headers = config.headers || {};
    (config.headers as any).Authorization = `Bearer ${token}`;
  }
  return config;
});

// ---------- Refresh-on-401 logic ----------
type Subscriber = (newToken: string | null) => void;
let isRefreshing = false;
let waitingRequests: Subscriber[] = [];

const subscribeForRefresh = (cb: Subscriber) => {
  waitingRequests.push(cb);
};

const broadcastNewToken = (newToken: string | null) => {
  waitingRequests.forEach((cb) => cb(newToken));
  waitingRequests = [];
};

// Module-scoped hook so AuthProvider can wire a final "kick to login" handler.
let onForceLogout: (() => void) | null = null;
export const setOnForceLogout = (fn: (() => void) | null) => {
  onForceLogout = fn;
};

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    const status = error.response?.status;
    const url = (originalRequest?.url || "").toString();

    // Only attempt refresh on a real 401, never on login/refresh endpoints themselves.
    const isAuthEndpoint =
      url.includes("/auth/login") ||
      url.includes("/auth/refresh") ||
      url.includes("/auth/register");

    if (status === 401 && !originalRequest._retry && !isAuthEndpoint) {
      originalRequest._retry = true;

      const refresh = await AsyncStorage.getItem(REFRESH_KEY);
      if (!refresh) {
        // No refresh token → can't recover, force logout
        if (onForceLogout) onForceLogout();
        return Promise.reject(error);
      }

      if (isRefreshing) {
        // Another request is already refreshing — wait for it
        return new Promise((resolve, reject) => {
          subscribeForRefresh((newToken) => {
            if (newToken) {
              originalRequest.headers = originalRequest.headers || {};
              (originalRequest.headers as any).Authorization = `Bearer ${newToken}`;
              resolve(api(originalRequest));
            } else {
              reject(error);
            }
          });
        });
      }

      isRefreshing = true;
      try {
        const resp = await axios.post(
          `${BASE_URL}/api/auth/refresh`,
          { refresh_token: refresh },
          { timeout: 15000 }
        );
        const newAccess: string | undefined = resp.data?.access_token;
        if (!newAccess) throw new Error("No access_token in refresh response");
        await AsyncStorage.setItem(ACCESS_KEY, newAccess);
        broadcastNewToken(newAccess);

        // Retry the original request with the fresh access token
        originalRequest.headers = originalRequest.headers || {};
        (originalRequest.headers as any).Authorization = `Bearer ${newAccess}`;
        return api(originalRequest);
      } catch (refreshErr) {
        // Refresh itself failed — clear both tokens and force logout
        broadcastNewToken(null);
        await AsyncStorage.removeItem(ACCESS_KEY);
        await AsyncStorage.removeItem(REFRESH_KEY);
        if (onForceLogout) onForceLogout();
        return Promise.reject(refreshErr);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

// ---------- Token helpers ----------
export const setToken = async (token: string | null) => {
  if (token) await AsyncStorage.setItem(ACCESS_KEY, token);
  else await AsyncStorage.removeItem(ACCESS_KEY);
};

export const setRefreshToken = async (token: string | null) => {
  if (token) await AsyncStorage.setItem(REFRESH_KEY, token);
  else await AsyncStorage.removeItem(REFRESH_KEY);
};

export const getToken = () => AsyncStorage.getItem(ACCESS_KEY);
export const getRefreshToken = () => AsyncStorage.getItem(REFRESH_KEY);

// ---------- Error formatting ----------
export function formatApiError(detail: any): string {
  if (detail == null) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}
