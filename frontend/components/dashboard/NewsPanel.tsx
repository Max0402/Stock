"use client";

// AI 新聞摘要面板：上方是「2 句 AI 摘要 + 市場影響評估」，下方是新聞列表（每則都有情緒標記）。

import { ExternalLink, Newspaper } from "lucide-react";
import useSWR from "swr";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { safeExternalUrl, timeAgo } from "@/lib/format";
import type { NewsResponse, SentimentLabel, SourceTier } from "@/lib/types";
import { cn } from "@/lib/utils";

import { SentimentBadge } from "./SentimentBadge";

const DOT: Record<SentimentLabel, string> = {
  Bullish: "bg-up",
  Bearish: "bg-down",
  Neutral: "bg-muted-foreground/50",
};

// 來源等級標籤：讓使用者一眼分辨「官方公告」與「一般媒體報導」
const TIER: Record<SourceTier, { label: string; className: string } | null> = {
  official: { label: "官方公告", className: "bg-emerald-500/15 text-emerald-300" },
  major: { label: "主流媒體", className: "bg-sky-500/15 text-sky-300" },
  press_release: { label: "公司新聞稿", className: "bg-muted text-muted-foreground" },
  other: null,
};

export function NewsPanel({ symbol }: { symbol: string }) {
  // 後端每小時更新一次，前端每 10 分鐘檢查一次就夠了
  const { data, error, isLoading } = useSWR<NewsResponse>(`/api/stocks/${encodeURIComponent(symbol)}/news`, {
    refreshInterval: 10 * 60_000,
  });
  const d = data?.digest;
  const sources = [...new Set(data?.articles.map((a) => a.source).filter(Boolean))];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Newspaper className="h-4 w-4" /> AI 新聞摘要 · {symbol}
        </CardTitle>
        {d && <span className="text-xs text-muted-foreground">更新於 {timeAgo(d.generated_at)}</span>}
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading && <p className="text-sm text-muted-foreground">分析新聞中…</p>}
        {error && <p className="text-sm text-red-400">無法載入新聞：{error.message}</p>}

        {d && (
          <div className="space-y-2 rounded-lg border border-border bg-muted/40 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <SentimentBadge sentiment={d} />
              <span className="text-xs text-muted-foreground tabular">
                情緒分數 {d.score > 0 ? "+" : ""}
                {d.score.toFixed(2)} · {d.article_count} 則重點新聞 · {d.method === "llm" ? "Claude AI" : "規則式 NLP"}
              </span>
            </div>
            <p className="text-sm leading-relaxed">📰 {d.summary}</p>
            <p className="text-sm leading-relaxed text-muted-foreground">📈 {d.impact}</p>
            {sources.length > 0 && (
              <p className="text-xs text-muted-foreground">來源：{sources.join("、")}</p>
            )}
          </div>
        )}

        {data && data.articles.length === 0 && <p className="text-sm text-muted-foreground">近期沒有相關新聞。</p>}

        <ul className="divide-y divide-border">
          {data?.articles.map((a) => {
            const href = safeExternalUrl(a.url);
            const tier = TIER[a.source_tier];
            return (
              <li key={`${a.url}|${a.title}`} className="flex gap-2.5 py-2">
                <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", DOT[a.sentiment_label])} title={a.sentiment_label} />
                <div className="min-w-0">
                  {href ? (
                    // rel="noopener noreferrer"：防止新分頁透過 window.opener 操控本頁（reverse tabnabbing）
                    <a href={href} target="_blank" rel="noopener noreferrer" className="group text-sm hover:underline">
                      {a.title}
                      <ExternalLink className="ml-1 inline h-3 w-3 opacity-0 group-hover:opacity-60" />
                    </a>
                  ) : (
                    <span className="text-sm">{a.title}</span>
                  )}
                  <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                    {tier && <span className={cn("rounded px-1.5 py-px text-[10px] font-medium", tier.className)}>{tier.label}</span>}
                    {a.source ?? "未知來源"} · {timeAgo(a.published_at)}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
