"""
ORM Models —— 對應 database/schema.sql 裡的資料表。

表格關係：
    users 1 ── N portfolios 1 ── N holdings
    users 1 ── N watchlist
    news_articles / news_digests / signal_snapshots 以「股票代碼」為單位（所有使用者共用）
    portfolio_snapshots 記錄每小時的投資組合市值（畫歷史走勢用）

小提醒：金額欄位在 PostgreSQL 用 NUMERIC（精確小數），
這裡設定 asdecimal=False 讓 Python 端拿到 float，方便跟 pandas 一起計算。
"""

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .db import Base


def utcnow() -> datetime:
    """一律以 UTC 儲存時間，顯示時再由前端轉成當地時區。"""
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """
    SQLite 不會儲存時區資訊，讀回來會變成「沒有時區」的 datetime，
    前端會誤以為是當地時間。這個型別保證「寫入轉 UTC、讀出補上 UTC」。
    （PostgreSQL 的 TIMESTAMPTZ 本來就正確，這層對它無害。）
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


Money = Numeric(20, 6, asdecimal=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    base_currency: Mapped[str] = mapped_column(String(3), default="TWD")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    portfolios: Mapped[list["Portfolio"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    watchlist: Mapped[list["WatchlistItem"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Portfolio(Base):
    __tablename__ = "portfolios"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100), default="我的投資組合")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    user: Mapped[User] = relationship(back_populates="portfolios")
    holdings: Mapped[list["Holding"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")


class Holding(Base):
    """一檔持股。avg_cost（平均成本）用來算損益；buy_price 是第一次買進價，僅供參考。"""

    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "symbol"),
        CheckConstraint("shares > 0", name="ck_holdings_shares_positive"),
        CheckConstraint("buy_price > 0", name="ck_holdings_buy_price_positive"),
        CheckConstraint("avg_cost > 0", name="ck_holdings_avg_cost_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(20))      # 例：AAPL、2330.TW
    market: Mapped[str] = mapped_column(String(2))       # "US" | "TW"
    currency: Mapped[str] = mapped_column(String(3))     # "USD" | "TWD"
    shares: Mapped[float] = mapped_column(Money)
    buy_price: Mapped[float] = mapped_column(Money)
    avg_cost: Mapped[float] = mapped_column(Money)
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    portfolio: Mapped[Portfolio] = relationship(back_populates="holdings")


class WatchlistItem(Base):
    """使用者按「⭐」收藏的股票。"""

    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("user_id", "symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(20))
    added_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    user: Mapped[User] = relationship(back_populates="watchlist")


class NewsArticle(Base):
    """抓到的單則新聞 + 情緒分數。url_hash 用來去重複（同一則新聞不會存兩次）。"""

    __tablename__ = "news_articles"
    __table_args__ = (
        UniqueConstraint("symbol", "url_hash"),
        Index("ix_news_articles_symbol_published", "symbol", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    url_hash: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(200))
    published_at: Mapped[datetime] = mapped_column(UTCDateTime())
    sentiment_score: Mapped[float] = mapped_column(Float)   # -1 ~ +1
    sentiment_label: Mapped[str] = mapped_column(String(10))  # Bullish / Bearish / Neutral
    importance: Mapped[float] = mapped_column(Float, default=0.0)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class NewsDigest(Base):
    """每小時為每檔股票產生一筆「AI 新聞摘要 + 市場影響評估」。"""

    __tablename__ = "news_digests"
    __table_args__ = (Index("ix_news_digests_symbol_generated", "symbol", "generated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    sentiment_label: Mapped[str] = mapped_column(String(10))
    sentiment_score: Mapped[float] = mapped_column(Float)
    summary: Mapped[str] = mapped_column(Text)   # 第 1 句：發生了什麼
    impact: Mapped[str] = mapped_column(Text)    # 第 2 句：對股價的可能影響
    article_count: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(10))  # "llm" | "rule"
    input_hash: Mapped[str] = mapped_column(String(64))  # 新聞沒變就不重新呼叫 AI（省錢）


class SignalSnapshot(Base):
    """每小時記錄一次買賣訊號，之後可以回測「訊號準不準」。"""

    __tablename__ = "signal_snapshots"
    __table_args__ = (Index("ix_signal_snapshots_symbol_computed", "symbol", "computed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    close: Mapped[float] = mapped_column(Money)
    rsi: Mapped[float] = mapped_column(Float)
    percent_b: Mapped[float] = mapped_column(Float)
    buy_zone_low: Mapped[float] = mapped_column(Money)
    buy_zone_high: Mapped[float] = mapped_column(Money)
    take_profit: Mapped[float] = mapped_column(Money)
    stop_loss: Mapped[float] = mapped_column(Money)
    trailing_stop: Mapped[float] = mapped_column(Money)
    action: Mapped[str] = mapped_column(String(12))
    score: Mapped[float] = mapped_column(Float)


class PortfolioSnapshot(Base):
    """每小時記錄投資組合總值（以 base currency 計）。"""

    __tablename__ = "portfolio_snapshots"
    __table_args__ = (Index("ix_portfolio_snapshots_portfolio_taken", "portfolio_id", "taken_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    taken_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    currency: Mapped[str] = mapped_column(String(3))
    market_value: Mapped[float] = mapped_column(Money)
    cost_basis: Mapped[float] = mapped_column(Money)
    unrealized_pnl: Mapped[float] = mapped_column(Money)
    day_pnl: Mapped[float] = mapped_column(Money)
