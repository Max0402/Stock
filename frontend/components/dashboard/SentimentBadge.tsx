import { Bot, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { Sentiment, SentimentLabel } from "@/lib/types";
import { cn } from "@/lib/utils";

const CONFIG: Record<SentimentLabel, { label: string; className: string }> = {
  Bullish: { label: "偏多 Bullish", className: "bg-up/15 text-up" },
  Bearish: { label: "偏空 Bearish", className: "bg-down/15 text-down" },
  Neutral: { label: "中性 Neutral", className: "bg-muted text-muted-foreground" },
};

export function SentimentBadge({ sentiment, className }: { sentiment: Sentiment; className?: string }) {
  const c = CONFIG[sentiment.label];
  // method = "llm" → Claude 產生的摘要（✨ 圖示）；"rule" → 規則式（🤖 圖示）
  const Icon = sentiment.method === "llm" ? Sparkles : Bot;
  return (
    <Badge
      className={cn(c.className, className)}
      title={`新聞情緒分數 ${sentiment.score.toFixed(2)}（${sentiment.method === "llm" ? "Claude AI 分析" : "規則式 NLP"}）`}
    >
      <Icon className="h-3 w-3" />
      {c.label}
    </Badge>
  );
}
