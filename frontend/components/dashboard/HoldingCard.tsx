"use client";

// 持股卡片：報價、損益、買賣建議、價位、新聞情緒、⭐ 收藏、編輯 / 刪除。
// 點擊卡片 → 右側 K 線圖切換成這檔股票。

import { Pencil, Trash2 } from "lucide-react";

import { Card } from "@/components/ui/card";
import { formatMoney, formatPct, formatPrice, formatShares, formatSigned } from "@/lib/format";
import { trendClass } from "@/lib/market-colors";
import type { Holding } from "@/lib/types";
import { cn } from "@/lib/utils";

import { PriceChange } from "./PriceChange";
import { SentimentBadge } from "./SentimentBadge";
import { SignalBadge } from "./SignalBadge";
import { SignalLevels } from "./SignalLevels";
import { StarButton } from "./StarButton";

function Stat({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={cn("truncate text-sm font-semibold tabular", className)} title={value}>
        {value}
      </div>
    </div>
  );
}

export function HoldingCard({
  holding: h,
  selected,
  onSelect,
  onEdit,
  onDelete,
}: {
  holding: Holding;
  selected: boolean;
  onSelect: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    // 整張卡片可以用滑鼠點選；鍵盤 / 螢幕閱讀器則使用代碼上的 <button>
    // （避免把星星、編輯等按鈕「巢狀」放在另一個 role=button 裡，那是無障礙設計的反模式）
    <Card
      onClick={onSelect}
      className={cn(
        "cursor-pointer space-y-3 p-4 transition-colors hover:border-primary/50",
        selected && "border-primary/70 bg-primary/5",
      )}
    >
      {/* ── 第一列：代碼、名稱、建議、操作按鈕 ── */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onSelect}
              aria-pressed={selected}
              aria-label={`在 K 線圖顯示 ${h.symbol}`}
              className="cursor-pointer rounded font-bold hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {h.symbol}
            </button>
            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
              {h.market === "TW" ? "台股" : "美股"}
            </span>
            {h.signal && <SignalBadge action={h.signal.action} />}
          </div>
          <div className="truncate text-xs text-muted-foreground">{h.name}</div>
        </div>
        <div className="flex shrink-0 items-center">
          <StarButton symbol={h.symbol} starred={h.starred} />
          <button
            type="button"
            onClick={(e) => (e.stopPropagation(), onEdit())}
            className="cursor-pointer rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label={`編輯 ${h.symbol}`}
          >
            <Pencil className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={(e) => (e.stopPropagation(), onDelete())}
            className="cursor-pointer rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-red-400"
            aria-label={`刪除 ${h.symbol}`}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      <PriceChange quote={h.quote} />

      {/* ── 損益數據（原幣別）── */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        <Stat label="持股" value={formatShares(h.shares, h.market)} />
        <Stat label="平均成本" value={formatPrice(h.avg_cost, h.currency)} />
        <Stat label="總市值" value={formatMoney(h.market_value, h.currency)} />
        <Stat
          label="未實現損益"
          value={formatSigned(h.unrealized_pnl, h.currency)}
          className={trendClass(h.unrealized_pnl)}
        />
        <Stat label="報酬率" value={formatPct(h.unrealized_pnl_pct)} className={trendClass(h.unrealized_pnl_pct)} />
        <Stat label="今日損益" value={formatSigned(h.day_pnl, h.currency)} className={trendClass(h.day_pnl)} />
      </div>

      {h.signal && <SignalLevels signal={h.signal} currency={h.currency} showTrailing />}

      {h.sentiment && (
        <div className="flex items-start gap-2 border-t border-border pt-2.5 text-xs">
          <SentimentBadge sentiment={h.sentiment} className="shrink-0" />
          <p className="line-clamp-2 text-muted-foreground">{h.sentiment.summary}</p>
        </div>
      )}
      {h.note && <p className="text-xs text-muted-foreground">📝 {h.note}</p>}
    </Card>
  );
}
