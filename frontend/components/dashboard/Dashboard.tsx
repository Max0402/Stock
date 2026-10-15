"use client";

// 主儀表板（Dashboard）
// ┌──────────────────────────────────────────────────────────┐
// │ Header：標題 · 漲跌色切換 · 重新整理                       │
// │ PortfolioSummary：總市值 / 未實現損益 / 今日損益 / 報酬率   │
// ├────────────────────┬─────────────────────────────────────┤
// │ 持股清單（卡片）     │ K 線圖（日K/週K、MA/RSI、買賣價位）     │
// │                    │ AI 新聞摘要                          │
// ├────────────────────┴─────────────────────────────────────┤
// │ ⭐ 追蹤清單                                               │
// │ 🔥 熱門藍籌股推薦                                         │
// └──────────────────────────────────────────────────────────┘
// 「目前選中的股票」是整頁共用的狀態：點任何卡片 → K 線與新聞切換到該股票。

import { LineChart, Plus, RefreshCw, ServerCrash } from "lucide-react";
import { useCallback, useState } from "react";
import useSWR, { useSWRConfig } from "swr";

import { KLineChart } from "@/components/chart/KLineChart";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Segmented } from "@/components/ui/segmented";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { type Convention, useMarketColors } from "@/lib/market-colors";
import type { Holding, Portfolio } from "@/lib/types";

import { HoldingCard } from "./HoldingCard";
import { HoldingFormDialog } from "./HoldingFormDialog";
import { NewsPanel } from "./NewsPanel";
import { PortfolioSummary } from "./PortfolioSummary";
import { Recommendations } from "./Recommendations";
import { WatchlistPanel } from "./WatchlistPanel";

const DEFAULT_SYMBOL = "2330.TW";

export function Dashboard() {
  // 每 60 秒自動更新報價（後端報價快取也是 60 秒）
  const { data, error, isLoading, isValidating } = useSWR<Portfolio>("/api/portfolio", { refreshInterval: 60_000 });
  const { mutate } = useSWRConfig();
  const { convention, setConvention } = useMarketColors();

  const [picked, setPicked] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Holding | null>(null);

  // 使用者還沒點選時，預設顯示第一檔持股
  const selected = picked ?? data?.holdings[0]?.symbol ?? DEFAULT_SYMBOL;

  const selectAndScroll = useCallback((symbol: string) => {
    setPicked(symbol);
    document.getElementById("chart")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const refreshAll = () => mutate((key) => typeof key === "string" && key.startsWith("/api/"));

  async function handleDelete(h: Holding) {
    if (!window.confirm(`確定要刪除 ${h.symbol}（${h.name}）的持股紀錄嗎？`)) return;
    try {
      await api.deleteHolding(h.id);
      if (picked === h.symbol) setPicked(null);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "刪除失敗");
    }
  }

  return (
    <main className="mx-auto max-w-[1440px] space-y-6 px-4 py-5 sm:px-6">
      {/* ── Header ── */}
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold sm:text-2xl">
            <LineChart className="h-6 w-6 text-primary" /> 我的股票儀表板
          </h1>
          <p className="text-xs text-muted-foreground">
            美股 + 台股 · 技術訊號 · AI 新聞情緒
            {data && ` · 報價更新於 ${timeAgo(data.updated_at)}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Segmented<Convention>
            ariaLabel="漲跌顏色"
            value={convention}
            onChange={setConvention}
            options={[
              { value: "tw", label: "紅漲綠跌" },
              { value: "us", label: "綠漲紅跌" },
            ]}
          />
          <Button variant="outline" size="icon" onClick={refreshAll} aria-label="重新整理" title="重新整理">
            <RefreshCw className={isValidating ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
          </Button>
        </div>
      </header>

      {/* ── 後端連不上時的提示 ── */}
      {error && (
        <Card className="flex items-start gap-3 border-red-500/40 bg-red-500/5 p-4 text-sm">
          <ServerCrash className="mt-0.5 h-5 w-5 shrink-0 text-red-400" />
          <div>
            <p className="font-medium text-red-300">無法連線到後端 API：{error.message}</p>
            <p className="mt-1 text-muted-foreground">
              請先啟動 FastAPI：<code className="rounded bg-muted px-1.5 py-0.5">cd backend && uvicorn app.main:app --reload</code>
            </p>
          </div>
        </Card>
      )}

      {/* ── 投資組合總覽 ── */}
      {data ? (
        <PortfolioSummary summary={data.summary} />
      ) : (
        isLoading && (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-[104px] animate-pulse rounded-xl bg-card" />
            ))}
          </div>
        )
      )}

      {/* ── 主區塊：持股清單 + K 線 / 新聞 ── */}
      <div className="grid gap-6 lg:grid-cols-12">
        <section className="space-y-3 lg:col-span-5 xl:col-span-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">
              持股清單 {data && <span className="text-sm font-normal text-muted-foreground">（{data.holdings.length}）</span>}
            </h2>
            <Button
              size="sm"
              onClick={() => {
                setEditing(null);
                setFormOpen(true);
              }}
            >
              <Plus className="h-4 w-4" /> 新增持股
            </Button>
          </div>

          {data?.holdings.length === 0 && (
            <p className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
              還沒有持股。點「新增持股」輸入代碼（如 AAPL、2330）、股數與成本，系統會自動計算損益。
            </p>
          )}
          <div className="space-y-3">
            {data?.holdings.map((h) => (
              <HoldingCard
                key={h.id}
                holding={h}
                selected={selected === h.symbol}
                onSelect={() => setPicked(h.symbol)}
                onEdit={() => {
                  setEditing(h);
                  setFormOpen(true);
                }}
                onDelete={() => handleDelete(h)}
              />
            ))}
          </div>
        </section>

        <section className="space-y-6 lg:col-span-7 xl:col-span-8">
          <KLineChart symbol={selected} />
          <NewsPanel symbol={selected} />
        </section>
      </div>

      <WatchlistPanel selected={selected} onSelect={selectAndScroll} />
      <Recommendations selected={selected} onSelect={selectAndScroll} />

      <footer className="border-t border-border pt-4 pb-8 text-xs leading-relaxed text-muted-foreground">
        ⚠️ 本工具的買賣訊號與 AI 摘要僅供學習與參考，不構成任何投資建議。報價可能有延遲；投資前請自行判斷並控管風險。
        <br />
        Charts by{" "}
        <a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer" className="underline">
          TradingView Lightweight Charts
        </a>
        .
      </footer>

      <HoldingFormDialog open={formOpen} onClose={() => setFormOpen(false)} editing={editing} />
    </main>
  );
}
