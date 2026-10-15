import type { Metadata } from "next";

import { Providers } from "@/components/providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "股票追蹤儀表板",
  description: "美股 + 台股持股管理、K 線技術分析、AI 新聞情緒摘要",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant" data-convention="tw">
      <body className="min-h-screen">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
