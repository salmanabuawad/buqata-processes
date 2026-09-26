import type { Metadata } from "next";
import { Heebo, Noto_Sans_Arabic } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const heebo = Heebo({ subsets: ["hebrew", "latin"], variable: "--font-heebo", display: "swap" });
const arabic = Noto_Sans_Arabic({ subsets: ["arabic"], variable: "--font-arabic", display: "swap" });

export const metadata: Metadata = {
  title: "מערכת רכש והגשות דיגיטלית — מועצה מקומית בוקעאתא",
  description: "Buq'ata Local Council — digital procurement and secure submissions",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="he" dir="rtl" className={`${heebo.variable} ${arabic.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
