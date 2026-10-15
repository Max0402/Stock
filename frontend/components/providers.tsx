"use client";

import { SWRConfig } from "swr";

import { fetcher } from "@/lib/api";
import { MarketColorsProvider } from "@/lib/market-colors";

/**
 * 全域 Provider：
 * - SWRConfig：所有 useSWR 共用同一個 fetcher；切回分頁時自動重新抓資料。
 * - MarketColorsProvider：紅漲綠跌 / 綠漲紅跌 切換。
 */
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig value={{ fetcher, revalidateOnFocus: true, shouldRetryOnError: false }}>
      <MarketColorsProvider>{children}</MarketColorsProvider>
    </SWRConfig>
  );
}
