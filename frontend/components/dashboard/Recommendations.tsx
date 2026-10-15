"use client";

// 熱門藍籌股推薦區：基本面簡介 + 目前 AI 評價（技術訊號 + 新聞情緒），可一鍵 ⭐ 加入追蹤。

import { Flame } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";

import { Segmented } from "@/components/ui/segmented";
import type { StockCard as StockCardData } from "@/lib/types";

import { StockCard } from "./StockCard";

type MarketFilter = "ALL" | "US" | "TW";

export function Recommendations({ selected, onSelect }: { selected: string; onSelect: (s: string) => void }) {
  const [market, setMarket] = useState<MarketFilter>("ALL");
  const { data, error, isLoading } = useSWR<StockCardData[]>(`/api/recommendations?market=${market}`, {
    refreshInterval: 5 * 60_000,
    keepPreviousData: true,
  });

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Flame className="h-5 w-5 text-orange-400" /> 熱門藍籌股
        </h2>
        <Segmented
          ariaLabel="市場"
          value={market}
          onChange={setMarket}
          options={[
            { value: "ALL", label: "全部" },
            { value: "US", label: "🇺🇸 美股" },
            { value: "TW", label: "🇹🇼 台股" },
          ]}
        />
      </div>
      {isLoading && !data && <p className="text-sm text-muted-foreground">載入中…</p>}
      {error && <p className="text-sm text-red-400">無法載入推薦清單：{error.message}</p>}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {data?.map((s) => (
          <StockCard
            key={s.symbol}
            stock={s}
            selected={selected === s.symbol}
            onSelect={() => onSelect(s.symbol)}
            showDescription
            showLevels={false}
          />
        ))}
      </div>
    </section>
  );
}
