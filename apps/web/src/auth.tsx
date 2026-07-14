import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

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

  const acceptAuth = (auth: AuthResponse) => {
    setUser(auth.user);
    setAccessToken(auth.token.access_token);
  };

  useEffect(() => {
    let active = true;
    api
      .refresh()
      .then((auth) => active && acceptAuth(auth))
      .catch(() => undefined)
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      accessToken,
      loading,
      login: async (email, password) => acceptAuth(await api.login(email, password)),
      register: async (payload) => acceptAuth(await api.register(payload)),
      logout: async () => {
        await api.logout().catch(() => undefined);
        setUser(null);
        setAccessToken(null);
      },
    }),
    [user, accessToken, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
