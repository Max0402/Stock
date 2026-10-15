"""
新聞來源：Google News RSS（免費、不需要 API Key）。

RSS 網址格式：
  美股（英文）：https://news.google.com/rss/search?q=NVIDIA+stock+when:2d&hl=en-US&gl=US&ceid=US:en
  台股（中文）：https://news.google.com/rss/search?q=台積電+2330+when:2d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant
  （when:2d = 只要近 2 天的新聞）

想改用 NewsAPI / Finnhub：寫一個回傳 list[RawArticle] 的函式，替換 fetch_news 即可。
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser
import httpx
import numpy as np

from ..config import get_settings
from .catalog import CATALOG
from .symbols import symbol_info

log = logging.getLogger(__name__)

MAX_AGE_HOURS = 48
MAX_ARTICLES = 20


@dataclass
class RawArticle:
    title: str
    url: str
    source: str | None
    published_at: datetime


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def news_query(symbol: str) -> str:
    if symbol in CATALOG:
        return CATALOG[symbol].news_query
    info = symbol_info(symbol)
    return f"{info.code} 股票" if info.market == "TW" else f"{info.code} stock"


def google_news_rss_url(symbol: str) -> str:
    q = quote_plus(f"{news_query(symbol)} when:2d")
    if symbol_info(symbol).market == "TW":
        return f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def _clean_title(title: str, source: str | None) -> str:
    # Google News 標題長這樣：「台積電法說會優於預期 - 經濟日報」→ 去掉後面的來源
    if source and title.endswith(f" - {source}"):
        return title[: -len(source) - 3].strip()
    return title.strip()


def fetch_google_news(symbol: str) -> list[RawArticle]:
    resp = httpx.get(
        google_news_rss_url(symbol),
        timeout=10.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (StockTracker; +https://github.com/)"},
    )
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    out: list[RawArticle] = []
    for e in feed.entries:
        if not e.get("published_parsed") or not e.get("link"):
            continue
        if not e.link.startswith(("https://", "http://")):
            continue  # 擋掉 javascript: 之類的連結，避免前端渲染時產生 XSS
        published = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
        if published < cutoff:
            continue
        source = (e.get("source") or {}).get("title")
        out.append(RawArticle(_clean_title(e.title, source), e.link, source, published))
    return out[:MAX_ARTICLES]


# ── Demo 新聞（離線開發用）──────────────────────────────────────────
_DEMO_EN = [
    "{n} beats estimates as data center demand stays strong",
    "{n} shares slide after analyst downgrade on valuation concerns",
    "{n} raises guidance for the full year, citing AI tailwinds",
    "{n} faces antitrust probe in Europe",
    "{n} announces $10B share buyback program",
    "{n} stock little changed ahead of earnings next week",
    "Supply shortage could delay {n} product launch",
    "{n} wins contract with major cloud provider",
]
_DEMO_ZH = [
    "{n}法說會優於預期，外資連三日買超",
    "{n}營收月增 12% 創新高，AI 訂單強勁",
    "{n}遭外資調降目標價，股價走弱",
    "{n}擴產計畫延後，市場擔憂需求放緩",
    "{n}董事會通過配息方案，殖利率約 2%",
    "{n}今日股價持平，成交量略減",
    "美國關稅政策不確定性升溫，{n}股價重挫",
    "{n}獲大單挹注，法人看好下半年旺季",
]


def fetch_demo_news(symbol: str) -> list[RawArticle]:
    info = symbol_info(symbol)
    name = CATALOG[symbol].name if symbol in CATALOG else info.code
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    hour_seed = int(now.timestamp() // 3600) ^ hash_int(symbol)
    rng = np.random.default_rng(hour_seed)
    templates = _DEMO_ZH if info.market == "TW" else _DEMO_EN
    picks = rng.choice(len(templates), size=4, replace=False)
    return [
        RawArticle(
            title=templates[i].format(n=name),
            url=f"https://example.com/demo-news/{info.code}/{now:%Y%m%d%H}/{i}",
            source="Demo News",
            published_at=now - timedelta(hours=int(rng.integers(0, 30))),
        )
        for i in picks
    ]


def hash_int(s: str) -> int:
    return int(hashlib.md5(s.encode()).hexdigest()[:8], 16)


def fetch_news(symbol: str) -> list[RawArticle]:
    if get_settings().data_provider == "demo":
        return fetch_demo_news(symbol)
    return fetch_google_news(symbol)
