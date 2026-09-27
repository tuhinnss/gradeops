"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { clearToken, getToken, setToken } from "./auth";
import { request } from "./client";
import type { AuthStatusResponse, TokenResponse, UserResponse } from "./types";

type SessionState =
  | { status: "loading"; user: null; authEnabled: boolean | null }
  | { status: "anonymous"; user: null; authEnabled: boolean | null }
  | { status: "authenticated"; user: UserResponse; authEnabled: boolean | null };

type SessionContextValue = SessionState & {
  login: (email: string, password: string) => Promise<UserResponse>;
  logout: () => void;
  refresh: () => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

function isUser(value: UserResponse | AuthStatusResponse): value is UserResponse {
  return "role" in value;
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<SessionState>({ status: "loading", user: null, authEnabled: null });

  const refresh = useCallback(async () => {
    let authEnabled: boolean | null = null;
    try {
      authEnabled = (await request<AuthStatusResponse>("/auth/status")).auth_enabled;
    } catch {
      /* API unreachable: treated as signed out below */
    }
    if (!getToken()) {
      setState({ status: "anonymous", user: null, authEnabled });
      return;
    }
    try {
      const me = await request<UserResponse | AuthStatusResponse>("/auth/me");
      if (isUser(me)) setState({ status: "authenticated", user: me, authEnabled });
      else setState({ status: "anonymous", user: null, authEnabled });
    } catch {
      clearToken();
      setState({ status: "anonymous", user: null, authEnabled });
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await request<TokenResponse>("/auth/login", { json: { email, password } });
      setToken(res.access_token);
      // Always confirm the role with the server rather than trusting the login payload.
      const me = await request<UserResponse | AuthStatusResponse>("/auth/me");
      if (!isUser(me)) throw new Error("Could not load your account");
      setState((s) => ({ status: "authenticated", user: me, authEnabled: s.authEnabled }));
      return me;
    },
    [],
  );

  const logout = useCallback(() => {
    clearToken();
    setState((s) => ({ status: "anonymous", user: null, authEnabled: s.authEnabled }));
    window.location.assign("/login");
  }, []);

  const value = useMemo(() => ({ ...state, login, logout, refresh }), [state, login, logout, refresh]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside <SessionProvider>");
  return ctx;
}
