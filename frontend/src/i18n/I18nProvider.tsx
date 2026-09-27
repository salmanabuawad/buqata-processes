"use client";

import { createContext, useContext, useEffect, useMemo, useSyncExternalStore } from "react";
import he from "./messages/he.json";
import ar from "./messages/ar.json";
import en from "./messages/en.json";

export type Locale = "he" | "ar" | "en";
type Messages = typeof he;

const MESSAGES: Record<Locale, Messages> = { he, ar: ar as Messages, en: en as Messages };
const STORAGE_KEY = "bdp_locale";

export const LOCALES: { code: Locale; label: string }[] = [
  { code: "he", label: "עברית" },
  { code: "ar", label: "العربية" },
  { code: "en", label: "English" },
];

type Vars = Record<string, string | number>;

interface I18n {
  locale: Locale;
  dir: "rtl" | "ltr";
  setLocale: (locale: Locale) => void;
  t: (key: string, vars?: Vars) => string;
  has: (key: string) => boolean;
  pick: (names: Partial<Record<Locale, string>> | undefined | null) => string;
}

const Ctx = createContext<I18n | null>(null);

function lookup(messages: Messages, key: string): string | undefined {
  let node: unknown = messages;
  for (const part of key.split(".")) {
    if (node && typeof node === "object" && part in (node as Record<string, unknown>)) {
      node = (node as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }
  return typeof node === "string" ? node : undefined;
}

function readStoredLocale(): Locale | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === "he" || value === "ar" || value === "en" ? value : null;
  } catch {
    return null;
  }
}

// The chosen locale is an external store (localStorage + this tab's memory),
// so every provider and other tabs stay in step without effect-driven state.
let chosenLocale: Locale | null = null;
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function currentLocale(): Locale {
  return chosenLocale ?? readStoredLocale() ?? "he";
}

function setLocale(next: Locale) {
  chosenLocale = next;
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* storage unavailable: the choice still applies for this visit */
  }
  listeners.forEach((listener) => listener());
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const locale = useSyncExternalStore(subscribe, currentLocale, () => "he" as Locale);
  const dir = locale === "en" ? "ltr" : "rtl";

  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = dir;
    document.title = lookup(MESSAGES[locale], "app.document_title") ?? document.title;
  }, [locale, dir]);

  const value = useMemo<I18n>(() => {
    const messages = MESSAGES[locale];
    return {
      locale,
      dir,
      setLocale,
      has: (key) => lookup(messages, key) !== undefined,
      t: (key, vars) => {
        let text = lookup(messages, key) ?? lookup(MESSAGES.he, key) ?? key;
        if (vars) for (const [k, v] of Object.entries(vars)) text = text.replaceAll(`{${k}}`, String(v));
        return text;
      },
      pick: (names) => (names ? names[locale] ?? names.he ?? names.en ?? "" : ""),
    };
  }, [locale, dir]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useI18n outside I18nProvider");
  return ctx;
}
