"use client";

import { I18nProvider } from "@/i18n/I18nProvider";
import { SessionProvider } from "@/lib/session";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <I18nProvider>
      <SessionProvider>{children}</SessionProvider>
    </I18nProvider>
  );
}
