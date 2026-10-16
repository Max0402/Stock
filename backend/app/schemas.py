"""
Pydantic Schemas —— API 的「輸入驗證」與「輸出格式」。

- *In  ：前端送進來的資料，FastAPI 會自動驗證（股數必須 > 0 等），不合法直接回 422。
- *Out ：回傳給前端的 JSON 結構；前端 lib/types.ts 有一份一模一樣的 TypeScript 型別。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .services.symbols import normalize_symbol


# ─────────────────────────── 輸入 ───────────────────────────
class HoldingIn(BaseModel):
    symbol: str = Field(examples=["AAPL", "2330.TW"])
    shares: float = Field(gt=0, description="持有股數（台股 1 張 = 1000 股）")
    buy_price: float = Field(gt=0, description="買入單價")
    avg_cost: float | None = Field(default=None, gt=0, description="平均成本；不填就等於買入單價")
    note: str | None = Field(default=None, max_length=500)

    @field_validator("symbol")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return normalize_symbol(v)  # 不合法會丟 ValueError → FastAPI 回 422


class HoldingUpdate(BaseModel):
    shares: float | None = Field(default=None, gt=0)
    buy_price: float | None = Field(default=None, gt=0)
    avg_cost: float | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=500)


class WatchlistIn(BaseModel):
    symbol: str

    @field_validator("symbol")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return normalize_symbol(v)


# ─────────────────────────── 輸出 ───────────────────────────
class QuoteOut(BaseModel):
    price: float
    prev_close: float
    change: float
    change_pct: float
    currency: str
    as_of: datetime


class SignalOut(BaseModel):
    action: Literal["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"]
    score: float
    technical_score: float
    news_score: float | None
    price: float
    rsi: float
    percent_b: float
    trend: Literal["UP", "DOWN", "SIDEWAYS"]
    buy_zone_low: float
    buy_zone_high: float
    take_profit: float
    stop_loss: float
    trailing_stop: float
    risk_reward: float
    zone_status: Literal["BELOW", "IN", "ABOVE"]
    reasons: list[str]


class SentimentOut(BaseModel):
    label: Literal["Bullish", "Bearish", "Neutral"]
    score: float
    summary: str
    impact: str
    method: Literal["llm", "rule"]
    article_count: int
    generated_at: datetime


class HoldingOut(BaseModel):
    id: int
    symbol: str
    name: str
    market: Literal["US", "TW"]
    currency: str
    shares: float
    buy_price: float
    avg_cost: float
    note: str | None
    quote: QuoteOut | None
    # ── 以下為自動計算（原幣別）──
    market_value: float | None
    cost_basis: float
    unrealized_pnl: float | None
    unrealized_pnl_pct: float | None
    day_pnl: float | None
    signal: SignalOut | None
    sentiment: SentimentOut | None
    starred: bool


class PortfolioSummaryOut(BaseModel):
    base_currency: str
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    day_pnl: float
    day_pnl_pct: float
    fx_rates: dict[str, float]  # 例：{"USD": 30.5, "TWD": 1}，代表 1 單位外幣 = 多少 base currency


class PortfolioOut(BaseModel):
    summary: PortfolioSummaryOut
    holdings: list[HoldingOut]
    updated_at: datetime


class StockCardOut(BaseModel):
    """Watchlist 與推薦區共用的股票卡片。"""

    symbol: str
    name: str
    market: Literal["US", "TW"]
    currency: str
    quote: QuoteOut | None
    signal: SignalOut | None
    sentiment: SentimentOut | None
    starred: bool
    sector: str | None = None
    description: str | None = None


class CandleOut(BaseModel):
    time: str  # "YYYY-MM-DD"，TradingView Lightweight Charts 直接吃這個格式
    open: float
    high: float
    low: float
    close: float
    volume: float


class LinePoint(BaseModel):
    time: str
    value: float


class MarkerOut(BaseModel):
    time: str
    type: Literal["BUY", "SELL"]
    price: float
    score: float


class ChartOut(BaseModel):
    symbol: str
    name: str
    interval: Literal["1d", "1wk"]
    candles: list[CandleOut]
    indicators: dict[str, list[LinePoint]]  # ma5 / ma20 / ma60 / bb_upper / bb_mid / bb_lower / rsi
    markers: list[MarkerOut]
    signal: SignalOut | None


class NewsArticleOut(BaseModel):
    title: str
    url: str
    source: str | None
    # official = 官方公告、major = 主流財經媒體、press_release = 公司新聞稿、other = 白名單以外
    source_tier: Literal["official", "major", "press_release", "other"]
    published_at: datetime
    sentiment_label: Literal["Bullish", "Bearish", "Neutral"]
    sentiment_score: float
    importance: float


class NewsOut(BaseModel):
    symbol: str
    digest: SentimentOut | None
    articles: list[NewsArticleOut]


class JobReportOut(BaseModel):
    symbols: int
    new_articles: int
    digests_created: int
    llm_calls: int
    signals_recorded: int
    portfolio_snapshots: int
    errors: list[str]
    duration_seconds: float
