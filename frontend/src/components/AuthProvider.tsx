"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, getJson, postJson, setCsrfToken } from "@/lib/api";
import type { MeResponse, User } from "@/lib/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<User>;
  register: (email: string, password: string, noticeVersion: string) => Promise<User>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getJson<MeResponse>("/api/v1/auth/me")
      .then((r) => { setCsrfToken(r.csrf_token); if (!cancelled) setUser(r.user); })
      .catch((e) => {
        setCsrfToken(null);
        // 401 just means "not logged in"; anything else (e.g. backend down) is worth telling the person.
        if (!cancelled && !(e instanceof ApiError && e.status === 401)) setError(e instanceof ApiError ? e.message : "Could not check your session.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const adopt = useCallback((r: MeResponse) => { setCsrfToken(r.csrf_token); setUser(r.user); setError(null); return r.user; }, []);
  const login = useCallback(async (email: string, password: string) => adopt(await postJson<MeResponse>("/api/v1/auth/login", { email, password })), [adopt]);
  const register = useCallback(async (email: string, password: string, noticeVersion: string) =>
    adopt(await postJson<MeResponse>("/api/v1/auth/register", { email, password, accept_notice_version: noticeVersion })), [adopt]);
  const logout = useCallback(async () => {
    try { await postJson("/api/v1/auth/logout", {}); } finally { setCsrfToken(null); setUser(null); }
  }, []);

  const value = useMemo(() => ({ user, loading, error, login, register, logout }), [user, loading, error, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

export const homeFor = (role: User["role"]) => (role === "reviewer" ? "/review" : role === "admin" ? "/admin" : "/dashboard");
