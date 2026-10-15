"use client";

// ⭐ 收藏按鈕：點一下加入 / 移出 Watchlist。
// 「樂觀更新（Optimistic UI）」：先立刻改變星星狀態，再背景呼叫 API；失敗才改回來。
// 這樣使用者不會感覺到網路延遲。

import { Star } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export function StarButton({ symbol, starred, className }: { symbol: string; starred: boolean; className?: string }) {
  const [optimistic, setOptimistic] = useState(starred);
  const [busy, setBusy] = useState(false);

  // 伺服器資料更新後，同步回元件狀態
  useEffect(() => setOptimistic(starred), [starred]);

  async function toggle(e: React.MouseEvent) {
    e.stopPropagation(); // 避免同時觸發卡片的 onClick（切換 K 線圖）
    if (busy) return;
    const next = !optimistic;
    setOptimistic(next);
    setBusy(true);
    try {
      await api.setStarred(symbol, next);
    } catch {
      setOptimistic(!next); // 失敗 → 還原
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={optimistic}
      aria-label={optimistic ? `從追蹤清單移除 ${symbol}` : `加入 ${symbol} 到追蹤清單`}
      title={optimistic ? "取消追蹤" : "加入追蹤"}
      className={cn(
        "cursor-pointer rounded-md p-1 transition-colors hover:bg-muted disabled:opacity-50",
        optimistic ? "text-yellow-400" : "text-muted-foreground hover:text-yellow-300",
        className,
      )}
      disabled={busy}
    >
      <Star className="h-4 w-4" fill={optimistic ? "currentColor" : "none"} />
    </button>
  );
}
