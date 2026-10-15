"use client";

// Watchlist 與推薦區共用的股票卡片。

import { Card } from "@/components/ui/card";
import type { StockCard as StockCardData } from "@/lib/types";
import { cn } from "@/lib/utils";

import { PriceChange } from "./PriceChange";
import { SentimentBadge } from "./SentimentBadge";
import { SignalBadge } from "./SignalBadge";
import { SignalLevels } from "./SignalLevels";
import { StarButton } from "./StarButton";

export function StockCard({
  stock: s,
  selected,
  onSelect,
  showDescription = false,
  showLevels = true,
}: {
  stock: StockCardData;
  selected?: boolean;
  onSelect: () => void;
  showDescription?: boolean;
  showLevels?: boolean;
}) {
  return (
    // 整張卡片可以用滑鼠點選；鍵盤 / 螢幕閱讀器則使用代碼上的 <button>
    // （避免把星星、編輯等按鈕「巢狀」放在另一個 role=button 裡，那是無障礙設計的反模式）
    <Card
      onClick={onSelect}
      className={cn(
        "flex cursor-pointer flex-col gap-3 p-4 transition-colors hover:border-primary/50",
        selected && "border-primary/70 bg-primary/5",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onSelect}
              aria-pressed={selected}
              aria-label={`在 K 線圖顯示 ${s.symbol}`}
              className="cursor-pointer rounded font-bold hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {s.symbol}
            </button>
            {s.signal && <SignalBadge action={s.signal.action} />}
          </div>
          <div className="truncate text-xs text-muted-foreground">
            {s.name}
            {s.sector && ` · ${s.sector}`}
          </div>
        </div>
        <StarButton symbol={s.symbol} starred={s.starred} />
      </div>

      <PriceChange quote={s.quote} size="sm" />

      {showDescription && s.description && (
        <p className="text-xs leading-relaxed text-muted-foreground">{s.description}</p>
      )}

      {showLevels && s.signal && <SignalLevels signal={s.signal} currency={s.currency} />}

      {s.sentiment && (
        <div className="mt-auto flex items-start gap-2 border-t border-border pt-2.5 text-xs">
          <SentimentBadge sentiment={s.sentiment} className="shrink-0" />
          <p className="line-clamp-2 text-muted-foreground" title={s.sentiment.impact}>
            {s.sentiment.impact}
          </p>
        </div>
      )}
    </Card>
  );
}
