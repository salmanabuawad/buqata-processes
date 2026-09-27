"use client";

import { createContext, useCallback, useContext, useEffect, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
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

async function loadMe(): Promise<Me | null> {
  try {
    return await api.get<Me>("/auth/me");
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) console.error(error);
    return null;
  }
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const { setLocale } = useI18n();
  const router = useRouter();

  const refresh = useCallback(async () => {
    const data = await loadMe();
    setMe(data);
    setLoading(false);
    return data;
  }, []);

  useEffect(() => {
    loadMe().then((data) => {
      setMe(data);
      setLoading(false);
    });
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      setMe(null);
      router.replace("/login/");
    }
  }, [router]);

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

const noSubscription = () => () => undefined;

// Static export: pages read their `?id=` on the client; the server render sees null.
export function useQueryParam(name: string): string | null {
  return useSyncExternalStore(
    noSubscription,
    () => new URLSearchParams(window.location.search).get(name),
    () => null,
  );
}
