import { cacheFetch, cacheGet, cacheInvalidate } from "./cache";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const TOKEN_KEY = "byte4bite_token";
const USER_KEY = "byte4bite_user";

export interface AuthUser {
  user_id: number;
  email: string;
}

export interface UserProfile {
  dietary_restriction?: string | null;
  allergies?: string[];
  health_goals?: string[];
}

export interface SessionUser extends AuthUser {
  profile?: UserProfile;
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  return raw ? (JSON.parse(raw) as AuthUser) : null;
}

export function setSession(token: string, user: AuthUser) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  cacheInvalidate("auth:");
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  cacheInvalidate();
}

export function parseApiError(data: unknown, fallback = "Request failed"): string {
  if (!data || typeof data !== "object") return fallback;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string };
    return first.msg || fallback;
  }
  const error = (data as { error?: string }).error;
  if (typeof error === "string") return error;
  return fallback;
}

export async function authFetch(path: string, options: RequestInit = {}) {
  const token = getToken();
  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401 && typeof window !== "undefined") {
    clearSession();
  }
  return res;
}

export async function authFetchJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await authFetch(path, options);
  return res.json() as Promise<T>;
}

export async function register(email: string, password: string) {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) {
    return { success: false, detail: parseApiError(data, "Registration failed") };
  }
  return data;
}

export async function login(email: string, password: string) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) {
    return { success: false, detail: parseApiError(data, "Invalid email or password") };
  }
  return data;
}

const ME_CACHE_KEY = "auth:me";
const SAVED_CACHE_KEY = "auth:saved";

export async function fetchMe(force = false): Promise<SessionUser | null> {
  if (!getToken()) return null;

  if (!force) {
    const cached = cacheGet<SessionUser>(ME_CACHE_KEY);
    if (cached) return cached;
  }

  return cacheFetch(
    ME_CACHE_KEY,
    async () => {
      const res = await authFetch("/api/auth/me");
      if (!res.ok) return null;
      const data = await res.json();
      if (!data.success) return null;
      return {
        user_id: data.user_id,
        email: data.email,
        profile: data.profile,
      } as SessionUser;
    },
    { ttlMs: 60_000, staleMs: 120_000 }
  );
}

export async function fetchProfile(force = false) {
  if (!getToken()) return null;
  const cacheKey = "auth:profile-full";
  if (!force) {
    const cached = cacheGet<{ success: boolean; profile: Record<string, unknown> }>(cacheKey);
    if (cached) return cached;
  }
  return cacheFetch(
    cacheKey,
    () => authFetchJson<{ success: boolean; profile: Record<string, unknown> }>("/api/auth/profile"),
    { ttlMs: 60_000 }
  );
}

export async function fetchSavedRecipes(force = false) {
  if (!getToken()) return { success: false, recipes: [], count: 0 };

  if (!force) {
    const cached = cacheGet<{ success: boolean; recipes: unknown[]; count: number }>(SAVED_CACHE_KEY);
    if (cached) return cached;
  }

  return cacheFetch(
    SAVED_CACHE_KEY,
    () =>
      authFetchJson<{ success: boolean; recipes: unknown[]; count: number }>(
        "/api/auth/saved-recipes"
      ),
    { ttlMs: 30_000, staleMs: 60_000 }
  );
}

export function invalidateAuthCache() {
  cacheInvalidate("auth:");
}

export async function saveRecipeToAccount(recipe: Record<string, unknown>, notes = "") {
  const res = await authFetch("/api/auth/saved-recipes", {
    method: "POST",
    body: JSON.stringify({ recipe, notes }),
  });
  const data = await res.json();
  if (data.success) {
    cacheInvalidate("auth:");
  }
  return { ok: res.ok, data };
}

export async function updateProfile(payload: Record<string, unknown>) {
  const res = await authFetch("/api/auth/profile", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (data.success) {
    invalidateAuthCache();
  }
  return { ok: res.ok, data };
}

/** Authenticated fetch for recipe generation (optional auth — attaches token when present). */
export async function recipeFetch(path: string, options: RequestInit = {}) {
  return authFetch(path, options);
}
