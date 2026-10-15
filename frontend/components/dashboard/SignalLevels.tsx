"use client";

// 買賣價位區塊：Buy Zone / 停利 Take Profit / 停損 Stop Loss（+ 持股才顯示的移動停損）
// 每個價位旁邊顯示「現價距離幾 %」，一眼看出離進出場點還有多遠。

import { ChevronDown } from "lucide-react";

import { distancePct, formatPct, formatPrice } from "@/lib/format";
import type { Signal } from "@/lib/types";
import { cn } from "@/lib/utils";

const ZONE_TEXT: Record<Signal["zone_status"], { text: string; className: string }> = {
  IN: { text: "✅ 現價位於買進區", className: "text-zone" },
  ABOVE: { text: "高於買進區，等待拉回", className: "text-muted-foreground" },
  BELOW: { text: "⚠️ 已跌破買進區，等待止穩", className: "text-stop" },
};

function Level({ label, value, colorClass }: { label: string; value: string; colorClass: string }) {
  return (
    <div className="min-w-0 rounded-lg bg-muted/60 px-2.5 py-1.5">
      <div className={cn("truncate text-[11px] font-medium", colorClass)}>{label}</div>
      <div className="truncate text-sm font-semibold tabular" title={value}>
        {value}
      </div>
    </div>
  );
}

export function SignalLevels({
  signal,
  currency,
  showTrailing = false,
}: {
  signal: Signal;
  currency: string;
  showTrailing?: boolean;
}) {
  const p = signal.price;
  const fmt = (v: number) => formatPrice(v, currency);
  const dist = (level: number) => formatPct(distancePct(level, p), 1); // 價位相對現價：+5% = 還要漲 5%
  const zone = ZONE_TEXT[signal.zone_status];
  const trailingHit = p <= signal.trailing_stop;

  // 持股卡片（showTrailing）用 2×2 格、完整中英標籤；其他卡片較窄，用精簡標籤並讓買進區欄位寬一點
  const full = showTrailing;
  return (
    <div className="space-y-2">
      <div className={cn("grid gap-2", full ? "grid-cols-2" : "grid-cols-[1.5fr_1fr_1fr]")}>
        <Level
          label={full ? "買進區 Buy Zone" : "買進區"}
          value={`${fmt(signal.buy_zone_low)}–${fmt(signal.buy_zone_high)}`}
          colorClass="text-zone"
        />
        <Level
          label={`${full ? "停利 Take Profit" : "停利"} ${dist(signal.take_profit)}`}
          value={fmt(signal.take_profit)}
          colorClass="text-target"
        />
        <Level
          label={`${full ? "停損 Stop Loss" : "停損"} ${dist(signal.stop_loss)}`}
          value={fmt(signal.stop_loss)}
          colorClass="text-stop"
        />
        {showTrailing && (
          <Level
            label={`移動停損 Trailing ${dist(signal.trailing_stop)}`}
            value={fmt(signal.trailing_stop)}
            colorClass={trailingHit ? "text-stop" : "text-muted-foreground"}
          />
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs">
        <span className={zone.className}>{zone.text}</span>
        <span className="text-muted-foreground tabular">
          RSI {signal.rsi.toFixed(0)} · %B {signal.percent_b.toFixed(2)} · 風報比 {signal.risk_reward.toFixed(1)}:1
        </span>
      </div>

      {/* <details> 原生可展開，手機點擊也能用；顯示演算法「為什麼」給出這個建議 */}
      <details className="group text-xs text-muted-foreground">
        <summary className="flex cursor-pointer list-none items-center gap-1 hover:text-foreground">
          <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
          為什麼是這個建議？
        </summary>
        <ul className="mt-1.5 list-disc space-y-0.5 pl-5">
          {signal.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
          <li>
            總分 {signal.score}（技術面 {signal.technical_score}
            {signal.news_score != null && `、新聞 ${(signal.news_score * 2).toFixed(1)}`}）：≥2 買進、≤−2 賣出
          </li>
        </ul>
      </details>
    </div>
  );
}
