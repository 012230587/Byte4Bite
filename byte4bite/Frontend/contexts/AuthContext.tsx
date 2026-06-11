"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  clearSession,
  fetchMe,
  getUser,
  invalidateAuthCache,
  login as apiLogin,
  register as apiRegister,
  setSession,
  type SessionUser,
  type UserProfile,
} from "@/services/auth";

interface AuthContextValue {
  user: SessionUser | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
  register: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
  refreshUser: (force?: boolean) => Promise<void>;
  profile: UserProfile | null;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async (force = false) => {
    const stored = getUser();
    if (!stored) {
      setUser(null);
      return;
    }
    const me = await fetchMe(force);
    if (me) {
      setUser(me);
    } else {
      clearSession();
      setUser(null);
    }
  }, []);

  useEffect(() => {
    refreshUser().finally(() => setLoading(false));
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const data = await apiLogin(email, password);
    if (!data.success) {
      return { success: false, error: data.detail || "Login failed" };
    }
    setSession(data.access_token, { user_id: data.user_id, email: data.email });
    invalidateAuthCache();
    await refreshUser(true);
    return { success: true };
  }, [refreshUser]);

  const register = useCallback(async (email: string, password: string) => {
    const data = await apiRegister(email, password);
    if (!data.success) {
      return { success: false, error: data.detail || "Registration failed" };
    }
    setSession(data.access_token, { user_id: data.user_id, email: data.email });
    invalidateAuthCache();
    await refreshUser(true);
    return { success: true };
  }, [refreshUser]);

  const logout = useCallback(() => {
    clearSession();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      isAuthenticated: Boolean(user),
      login,
      register,
      logout,
      refreshUser,
      profile: user?.profile ?? null,
    }),
    [user, loading, login, register, logout, refreshUser]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}

export function useRequireAuth(redirectPath = "/signin") {
  const auth = useAuth();
  useEffect(() => {
    if (!auth.loading && !auth.isAuthenticated && typeof window !== "undefined") {
      const next = encodeURIComponent(window.location.pathname);
      window.location.href = `${redirectPath}?next=${next}`;
    }
  }, [auth.loading, auth.isAuthenticated, redirectPath]);
  return auth;
}
