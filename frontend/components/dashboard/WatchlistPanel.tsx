"use client";

// ⭐ 自訂追蹤清單：顯示使用者收藏的股票（報價、訊號、情緒）。

import { Star } from "lucide-react";
import useSWR from "swr";

import type { StockCard as StockCardData } from "@/lib/types";

import { StockCard } from "./StockCard";

export function WatchlistPanel({ selected, onSelect }: { selected: string; onSelect: (s: string) => void }) {
  const { data, isLoading } = useSWR<StockCardData[]>("/api/watchlist", { refreshInterval: 60_000 });

  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-2 text-lg font-semibold">
        <Star className="h-5 w-5 text-yellow-400" fill="currentColor" /> 追蹤清單
        {data && <span className="text-sm font-normal text-muted-foreground">（{data.length}）</span>}
      </h2>
      {isLoading && <p className="text-sm text-muted-foreground">載入中…</p>}
      {data?.length === 0 && (
        <p className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
          還沒有追蹤的股票。點擊任何卡片右上角的 ☆，或從下方「熱門藍籌股」一鍵加入。
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {data?.map((s) => (
          <StockCard key={s.symbol} stock={s} selected={selected === s.symbol} onSelect={() => onSelect(s.symbol)} />
        ))}
      </div>
    </section>
  );
}
