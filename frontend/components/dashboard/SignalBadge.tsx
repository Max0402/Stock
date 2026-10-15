// 買賣建議標籤：強力買進 / 買進 / 觀望 / 賣出 / 強力賣出
// 顏色跟著「漲跌慣例」走：買進 = 看漲色（台灣紅），賣出 = 看跌色（台灣綠）。

import { Badge } from "@/components/ui/badge";
import type { Action } from "@/lib/types";
import { cn } from "@/lib/utils";

const CONFIG: Record<Action, { label: string; className: string }> = {
  STRONG_BUY: { label: "強力買進", className: "bg-up text-white" },
  BUY: { label: "買進", className: "bg-up/15 text-up ring-1 ring-up/40" },
  HOLD: { label: "觀望", className: "bg-muted text-muted-foreground ring-1 ring-border" },
  SELL: { label: "賣出", className: "bg-down/15 text-down ring-1 ring-down/40" },
  STRONG_SELL: { label: "強力賣出", className: "bg-down text-white" },
};

export function SignalBadge({ action, score, className }: { action: Action; score?: number; className?: string }) {
  const c = CONFIG[action];
  return (
    <Badge className={cn(c.className, className)} title={score != null ? `訊號分數 ${score}` : undefined}>
      {c.label}
      {score != null && <span className="tabular opacity-75">{score > 0 ? `+${score}` : score}</span>}
    </Badge>
  );
}
