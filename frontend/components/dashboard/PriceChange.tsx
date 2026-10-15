"use client";

import { ArrowDownRight, ArrowUpRight } from "lucide-react";

import { formatPct, formatPrice } from "@/lib/format";
import { trendClass } from "@/lib/market-colors";
import type { Quote } from "@/lib/types";
import { cn } from "@/lib/utils";

/** 現價 + 日漲跌（金額與 %），顏色依漲跌慣例。 */
export function PriceChange({ quote, size = "md" }: { quote: Quote | null; size?: "sm" | "md" }) {
  if (!quote) return <span className="text-sm text-muted-foreground">報價暫不可用</span>;
  const Arrow = quote.change >= 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <div className={cn("flex items-baseline gap-2 tabular", size === "sm" && "gap-1.5")}>
      <span className={cn("font-semibold", size === "md" ? "text-xl" : "text-base")}>
        {formatPrice(quote.price, quote.currency)}
      </span>
      <span className={cn("flex items-center text-xs font-medium", trendClass(quote.change))}>
        <Arrow className="h-3.5 w-3.5" />
        {formatPrice(Math.abs(quote.change), quote.currency)} ({formatPct(quote.change_pct)})
      </span>
    </div>
  );
}
