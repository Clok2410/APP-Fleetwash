import React, { createContext, useContext, useEffect, useState } from "react";
import { api, setToken, getToken, formatApiError } from "./api";

export type User = {
  id: string;
  email: string;
  name: string;
  role: "admin" | "staff";
  holiday_entitlement?: number;
};

type AuthCtx = {
  user: User | null | undefined; // undefined = loading, null = logged out
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined);

  const refresh = async () => {
    try {
      const t = await getToken();
      if (!t) {
        setUser(null);
        return;
      }
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch {
      await setToken(null);
      setUser(null);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const login = async (email: string, password: string) => {
    try {
      const { data } = await api.post("/auth/login", { email, password });
      await setToken(data.access_token);
      setUser(data.user);
    } catch (e: any) {
      throw new Error(formatApiError(e.response?.data?.detail) || e.message);
    }
  };

  const logout = async () => {
    await setToken(null);
    setUser(null);
  };

  return <Ctx.Provider value={{ user, login, logout, refresh }}>{children}</Ctx.Provider>;
}

export const useAuth = () => {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth must be inside AuthProvider");
  return c;
};
