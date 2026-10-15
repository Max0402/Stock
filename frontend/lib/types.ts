// 與後端 backend/app/schemas.py 一一對應的 TypeScript 型別。
// 後端改欄位時記得同步更新這裡，TypeScript 就會幫你找出所有要改的地方。

export type Market = "US" | "TW";
export type Action = "STRONG_BUY" | "BUY" | "HOLD" | "SELL" | "STRONG_SELL";
export type SentimentLabel = "Bullish" | "Bearish" | "Neutral";
export type Interval = "1d" | "1wk";

export interface Quote {
  price: number;
  prev_close: number;
  change: number;
  change_pct: number;
  currency: string;
  as_of: string;
}

export interface Signal {
  action: Action;
  score: number;
  technical_score: number;
  news_score: number | null;
  price: number;
  rsi: number;
  percent_b: number;
  trend: "UP" | "DOWN" | "SIDEWAYS";
  buy_zone_low: number;
  buy_zone_high: number;
  take_profit: number;
  stop_loss: number;
  trailing_stop: number;
  risk_reward: number;
  zone_status: "BELOW" | "IN" | "ABOVE";
  reasons: string[];
}

export interface Sentiment {
  label: SentimentLabel;
  score: number;
  summary: string;
  impact: string;
  method: "llm" | "rule";
  article_count: number;
  generated_at: string;
}

export interface Holding {
  id: number;
  symbol: string;
  name: string;
  market: Market;
  currency: string;
  shares: number;
  buy_price: number;
  avg_cost: number;
  note: string | null;
  quote: Quote | null;
  market_value: number | null;
  cost_basis: number;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  day_pnl: number | null;
  signal: Signal | null;
  sentiment: Sentiment | null;
  starred: boolean;
}

export interface PortfolioSummary {
  base_currency: string;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  day_pnl: number;
  day_pnl_pct: number;
  fx_rates: Record<string, number>;
}

export interface Portfolio {
  summary: PortfolioSummary;
  holdings: Holding[];
  updated_at: string;
}

export interface StockCard {
  symbol: string;
  name: string;
  market: Market;
  currency: string;
  quote: Quote | null;
  signal: Signal | null;
  sentiment: Sentiment | null;
  starred: boolean;
  sector?: string | null;
  description?: string | null;
}

export interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface LinePoint {
  time: string;
  value: number;
}

export interface ChartMarker {
  time: string;
  type: "BUY" | "SELL";
  price: number;
  score: number;
}

export interface ChartData {
  symbol: string;
  name: string;
  interval: Interval;
  candles: Candle[];
  indicators: Record<"ma5" | "ma20" | "ma60" | "bb_upper" | "bb_mid" | "bb_lower" | "rsi", LinePoint[]>;
  markers: ChartMarker[];
  signal: Signal | null;
}

export interface NewsArticle {
  title: string;
  url: string;
  source: string | null;
  published_at: string;
  sentiment_label: SentimentLabel;
  sentiment_score: number;
  importance: number;
}

export interface NewsResponse {
  symbol: string;
  digest: Sentiment | null;
  articles: NewsArticle[];
}

export interface HoldingInput {
  symbol: string;
  shares: number;
  buy_price: number;
  avg_cost?: number | null;
  note?: string | null;
}
