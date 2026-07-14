import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api } from "./api";
import type { AuthResponse, RegisterRequest, User } from "./types";

interface AuthState {
  user: User | null;
  accessToken: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const acceptAuth = useCallback((auth: AuthResponse) => {
    setUser(auth.user);
    setAccessToken(auth.token.access_token);
  }, []);

  const clearAuth = useCallback(() => {
    setUser(null);
    setAccessToken(null);
  }, []);

  useEffect(() => {
    let active = true;
    const unsubscribe = api.subscribeAuth((auth) => {
      if (!active) return;
      if (auth) acceptAuth(auth);
      else clearAuth();
    });
    api
      .refresh()
      .catch(() => undefined)
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
      unsubscribe();
    };
  }, [acceptAuth, clearAuth]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      accessToken,
      loading,
      login: async (email, password) => {
        await api.login(email, password);
      },
      register: async (payload) => {
        await api.register(payload);
      },
      logout: async () => {
        await api.logout().catch(() => undefined);
        clearAuth();
      },
    }),
    [user, accessToken, loading, clearAuth],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
