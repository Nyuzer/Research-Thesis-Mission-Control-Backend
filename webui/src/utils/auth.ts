import { create } from "zustand";

export type UserRole = "admin" | "operator" | "viewer";

export interface AuthUser {
  id: string;
  email: string;
  username: string;
  role: UserRole;
  created_at: string;
  last_login: string | null;
  is_active: boolean;
}

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: AuthUser | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  setAuth: (token: string, refreshToken: string, user: AuthUser) => void;
  refresh: () => Promise<boolean>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem("access_token"),
  refreshToken: localStorage.getItem("refresh_token"),
  user: (() => {
    try {
      const u = localStorage.getItem("auth_user");
      return u ? JSON.parse(u) : null;
    } catch {
      return null;
    }
  })(),
  isAuthenticated: !!localStorage.getItem("access_token"),

  setAuth: (token, refreshToken, user) => {
    localStorage.setItem("access_token", token);
    localStorage.setItem("refresh_token", refreshToken);
    localStorage.setItem("auth_user", JSON.stringify(user));
    set({ token, refreshToken, user, isAuthenticated: true });
  },

  login: async (email, password) => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Login failed");
    }
    const data = await res.json();
    get().setAuth(data.access_token, data.refresh_token, data.user);
  },

  logout: () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("auth_user");
    set({ token: null, refreshToken: null, user: null, isAuthenticated: false });
  },

  refresh: async () => {
    const rt = get().refreshToken;
    if (!rt) return false;
    try {
      const res = await fetch(`/api/auth/refresh?refresh_token=${encodeURIComponent(rt)}`, {
        method: "POST",
      });
      if (!res.ok) return false;
      const data = await res.json();
      get().setAuth(data.access_token, data.refresh_token, data.user);
      return true;
    } catch {
      return false;
    }
  },
}));

export function getAuthHeaders(): Record<string, string> {
  const token = useAuthStore.getState().token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}
