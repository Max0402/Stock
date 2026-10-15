"use client";

// 頂部 4 個統計卡：總市值、未實現損益、今日損益、總報酬率（皆換算為 base currency）。

import { Activity, CalendarClock, PiggyBank, TrendingUp } from "lucide-react";

import { Card } from "@/components/ui/card";
import { formatMoney, formatPct, formatSigned } from "@/lib/format";
import { trendClass } from "@/lib/market-colors";
import type { PortfolioSummary as Summary } from "@/lib/types";
import { cn } from "@/lib/utils";

function Tile({
  icon: Icon,
  label,
  value,
  sub,
  valueClass,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  sub?: string;
  valueClass?: string;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Icon className="h-4 w-4" />
        {label}
      </div>
      <div className={cn("mt-1.5 truncate text-xl font-bold tabular sm:text-2xl", valueClass)} title={value}>
        {value}
      </div>
      {sub && <div className="mt-0.5 truncate text-xs text-muted-foreground tabular">{sub}</div>}
    </Card>
  );
}

export function PortfolioSummary({ summary: s }: { summary: Summary }) {
  const ccy = s.base_currency;
  const fxText = Object.entries(s.fx_rates)
    .filter(([c]) => c !== ccy)
    .map(([c, r]) => `1 ${c} = ${r.toFixed(2)} ${ccy}`)
    .join(" · ");

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Tile icon={PiggyBank} label={`總市值（${ccy}）`} value={formatMoney(s.market_value, ccy)} sub={fxText || "—"} />
      <Tile
        icon={TrendingUp}
        label="未實現損益"
        value={formatSigned(s.unrealized_pnl, ccy)}
        sub={`成本 ${formatMoney(s.cost_basis, ccy)}`}
        valueClass={trendClass(s.unrealized_pnl)}
      />
      <Tile
        icon={CalendarClock}
        label="今日損益"
        value={formatSigned(s.day_pnl, ccy)}
        sub={formatPct(s.day_pnl_pct)}
        valueClass={trendClass(s.day_pnl)}
      />
      <Tile
        icon={Activity}
        label="總報酬率"
        value={formatPct(s.unrealized_pnl_pct)}
        sub="（市值 − 成本）÷ 成本"
        valueClass={trendClass(s.unrealized_pnl_pct)}
      />
    </div>
  );
}
