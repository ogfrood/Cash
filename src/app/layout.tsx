import type { Metadata, Viewport } from "next";
import "./globals.css";

import { TabBar } from "@/components/TabBar";

export const metadata: Metadata = {
  title: "Cash",
  description: "Gestor financeiro pessoal — salário semanal, caixinhas e metas.",
};

export const viewport: Viewport = {
  themeColor: "#000000",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" className="h-full">
      <body className="min-h-full">
        <main className="mx-auto max-w-[520px] px-5 pt-6 pb-32">
          {children}
        </main>
        <TabBar />
      </body>
    </html>
  );
}
