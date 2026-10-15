"use client";

// 漲跌顏色慣例切換：
//   台股 / 亞洲：紅漲綠跌 🔴📈
//   美股 / 歐美：綠漲紅跌 🟢📈
// 做法：在 <html data-convention="tw|us"> 切換，CSS 變數 --color-up / --color-down 會跟著互換，
// 所有用 text-up / bg-down 的元件自動變色；K 線圖（canvas）則從這裡拿 hex 色碼。

import { createContext, useCallback, useContext, useEffect, useState } from "react";

export type Convention = "tw" | "us";

const RED = "#ef4444";
const GREEN = "#22c55e";
const STORAGE_KEY = "color-convention";

interface MarketColors {
  convention: Convention;
  setConvention: (c: Convention) => void;
  upHex: string;
  downHex: string;
}

const Ctx = createContext<MarketColors | null>(null);

export function MarketColorsProvider({ children }: { children: React.ReactNode }) {
  const [convention, setState] = useState<Convention>("tw");

  // 讀取上次的偏好（localStorage 在無痕模式可能會丟錯，所以要 try/catch）
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === "tw" || saved === "us") setState(saved);
    } catch {
      /* 忽略 */
    }
  }, []);

  useEffect(() => {
    document.documentElement.dataset.convention = convention;
  }, [convention]);

  const setConvention = useCallback((c: Convention) => {
    setState(c);
    try {
      localStorage.setItem(STORAGE_KEY, c);
    } catch {
      /* 忽略 */
    }
  }, []);

  const value: MarketColors = {
    convention,
    setConvention,
    upHex: convention === "tw" ? RED : GREEN,
    downHex: convention === "tw" ? GREEN : RED,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useMarketColors(): MarketColors {
  const v = useContext(Ctx);
  if (!v) throw new Error("useMarketColors must be used inside <MarketColorsProvider>");
  return v;
}

/** 依數值正負回傳 Tailwind class：正 → text-up、負 → text-down */
export function trendClass(value: number | null | undefined): string {
  if (value == null || value === 0) return "text-muted-foreground";
  return value > 0 ? "text-up" : "text-down";
}
