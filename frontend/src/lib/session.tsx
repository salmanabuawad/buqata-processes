"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError } from "./api";
import { useI18n, type Locale } from "@/i18n/I18nProvider";

export interface Me {
  id: string;
  email: string;
  full_name: string;
  kind: "staff" | "supplier" | "applicant";
  locale: Locale;
  roles: string[];
  permissions: string[];
  mfa: boolean;
  supplier: { id: string; company_name: string } | null;
  unread_notifications: number;
}

interface SessionState {
  me: Me | null;
  loading: boolean;
  refresh: () => Promise<Me | null>;
  logout: () => Promise<void>;
  can: (permission: string) => boolean;
}

const Ctx = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const { setLocale } = useI18n();

  const refresh = useCallback(async () => {
    try {
      const data = await api.get<Me>("/auth/me");
      setMe(data);
      return data;
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) console.error(error);
      setMe(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      setMe(null);
      window.location.href = "/login/";
    }
  }, []);

  // The UI language follows the browser choice; the account locale only seeds it once.
  useEffect(() => {
    if (me && typeof window !== "undefined") {
      try {
        if (!window.localStorage.getItem("bdp_locale")) setLocale(me.locale);
      } catch {
        /* ignore */
      }
    }
  }, [me, setLocale]);

  const can = useCallback((permission: string) => !!me?.permissions.includes(permission), [me]);

  return <Ctx.Provider value={{ me, loading, refresh, logout, can }}>{children}</Ctx.Provider>;
}

export function useSession(): SessionState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSession outside SessionProvider");
  return ctx;
}

export function useQueryParam(name: string): string | null {
  const [value, setValue] = useState<string | null>(null);
  useEffect(() => {
    setValue(new URLSearchParams(window.location.search).get(name));
  }, [name]);
  return value;
}
