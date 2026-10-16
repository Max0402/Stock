"""
多來源新聞抓取：Yahoo Finance + Google News（可信媒體）+ 證交所重大訊息 + Finnhub。

整體流程（fetch_news）
----------------------
    ┌ Yahoo Finance 個股新聞 ─┐
    ├ Google News RSS ───────┤   平行抓取     過濾：近 48 小時、http(s) 連結、
    ├ 證交所重大訊息（.TW）───┼──────────────→ 可信來源白名單 → 跨來源去重複 → 依時間排序
    └ Finnhub（美股，選用）───┘   （一個來源失敗不影響其他來源）

每個來源都有獨立的 parse_* 函式（輸入原始資料 → 輸出 RawArticle），
這樣單元測試可以餵「假的回應」來測，不需要真的連網路。

各來源網址
----------
  Yahoo  ：yfinance 的 Ticker.get_news()（內部呼叫 finance.yahoo.com）
  Google ：https://news.google.com/rss/search?q=<關鍵字> (site:reuters.com OR …) when:2d&hl=…
  TWSE   ：https://openapi.twse.com.tw/v1/opendata/t187ap04_L（上市公司每日重大訊息）
  Finnhub：https://finnhub.io/api/v1/company-news?symbol=AAPL&from=…&to=…
"""

import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser
import httpx
import numpy as np

from ..config import get_settings
from .cache import TTLCache
from .catalog import CATALOG
from .news_sources import TIER_RANK, classify_source, google_site_filter
from .symbols import symbol_info

log = logging.getLogger(__name__)

MAX_AGE_HOURS = 48
MAX_ARTICLES = 30
HTTP_TIMEOUT = 10.0
USER_AGENT = "Mozilla/5.0 (compatible; StockTracker/0.1)"
TAIPEI = timezone(timedelta(hours=8))

TWSE_ANNOUNCEMENTS_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"
MOPS_URL = "https://mops.twse.com.tw/"
FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/company-news"


class NewsUnavailableError(RuntimeError):
    """所有新聞來源都失敗（通常是網路問題）。"""


@dataclass
class RawArticle:
    title: str
    url: str
    source: str | None              # 發布者，例如 "Reuters"、"經濟日報"
    published_at: datetime
    provider: str = "google"        # 從哪個管道抓到：yahoo / google / twse / finnhub / demo
    source_url: str | None = None   # 發布者網址（判斷是否為可信來源用）
    uid: str | None = None          # 去重複用的唯一鍵；預設就是 url

    @property
    def key(self) -> str:
        return self.uid or self.url

    @property
    def tier(self) -> str:
        s = classify_source(self.source, self.source_url or self.url)
        return s.tier if s else "other"


def url_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def title_key(title: str) -> str:
    """
    標題「指紋」：轉小寫、去掉標點與空白，取前 50 字。
    同一則新聞被路透和 Yahoo 同時刊出時，網址不同但指紋相同 → 只留一筆。
    """
    return re.sub(r"[\W_]+", "", title.lower())[:50]


def _is_http(url: str | None) -> bool:
    # 只接受 http(s)：擋掉 javascript: 之類的連結，避免前端渲染時產生 XSS
    return bool(url) and url.startswith(("https://", "http://"))


def news_query(symbol: str) -> str:
    if symbol in CATALOG:
        return CATALOG[symbol].news_query
    info = symbol_info(symbol)
    return f"{info.code} 股票" if info.market == "TW" else f"{info.code} stock"


# ═════════════════════════════════════════════════════════════════════
# 1) Yahoo Finance
# ═════════════════════════════════════════════════════════════════════
def parse_yahoo_news(items: list[dict]) -> list[RawArticle]:
    """
    yfinance 新版格式：{"id": ..., "content": {"title", "pubDate", "provider": {"displayName"},
                                             "canonicalUrl": {"url"}, "clickThroughUrl": {"url"}}}
    舊版格式（相容）：{"title", "link", "publisher", "providerPublishTime"}
    """
    out: list[RawArticle] = []
    for item in items:
        c = item.get("content") or item
        if c.get("contentType") not in (None, "STORY"):
            continue  # 跳過影片等非文章內容
        title = (c.get("title") or "").strip()
        canonical = (c.get("canonicalUrl") or {}).get("url")
        click = (c.get("clickThroughUrl") or {}).get("url")
        url = canonical or click or c.get("link")
        provider = c.get("provider") or {}
        source = provider.get("displayName") or c.get("publisher")

        if c.get("pubDate"):
            published = datetime.fromisoformat(c["pubDate"].replace("Z", "+00:00"))
        elif c.get("providerPublishTime"):
            published = datetime.fromtimestamp(int(c["providerPublishTime"]), tz=timezone.utc)
        else:
            continue
        if title and _is_http(url):
            out.append(RawArticle(title, url, source, published, "yahoo", provider.get("url") or url))
    return out


def fetch_yahoo_news(symbol: str) -> list[RawArticle]:
    import yfinance as yf

    return parse_yahoo_news(yf.Ticker(symbol).get_news(count=20))


# ═════════════════════════════════════════════════════════════════════
# 2) Google News RSS（只搜尋可信媒體）
# ═════════════════════════════════════════════════════════════════════
def google_news_rss_url(symbol: str, trusted_only: bool = True) -> str:
    market = symbol_info(symbol).market
    query = news_query(symbol)
    if trusted_only:
        query += " " + google_site_filter(market)
    q = quote_plus(f"{query} when:2d")
    if market == "TW":
        return f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def _clean_title(title: str, source: str | None) -> str:
    # Google News 標題長這樣：「台積電法說會優於預期 - 經濟日報」→ 去掉後面的來源
    if source and title.endswith(f" - {source}"):
        return title[: -len(source) - 3].strip()
    return title.strip()


def parse_google_rss(content: bytes) -> list[RawArticle]:
    out: list[RawArticle] = []
    for e in feedparser.parse(content).entries:
        if not e.get("published_parsed") or not _is_http(e.get("link")):
            continue
        src = e.get("source") or {}
        source, source_url = src.get("title"), src.get("href")
        published = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
        out.append(RawArticle(_clean_title(e.title, source), e.link, source, published, "google", source_url))
    return out


def fetch_google_news(symbol: str) -> list[RawArticle]:
    resp = httpx.get(
        google_news_rss_url(symbol, get_settings().news_trusted_only),
        timeout=HTTP_TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    return parse_google_rss(resp.content)


# ═════════════════════════════════════════════════════════════════════
# 3) 證交所 OpenAPI：上市公司每日重大訊息（官方第一手資料）
# ═════════════════════════════════════════════════════════════════════
def _roc_datetime(date_s: str, time_s: str) -> datetime | None:
    """民國日期 '1151016' + 時間 '143005'（台北時間）→ UTC datetime。"""
    d, t = date_s.strip(), time_s.strip().zfill(6)
    if len(d) < 7 or not d.isdigit() or not t.isdigit():
        return None
    local = datetime(int(d[:-4]) + 1911, int(d[-4:-2]), int(d[-2:]), int(t[:2]), int(t[2:4]), int(t[4:6]), tzinfo=TAIPEI)
    return local.astimezone(timezone.utc)


def parse_twse_announcements(rows: list[dict], code: str) -> list[RawArticle]:
    out: list[RawArticle] = []
    for raw in rows:
        # 證交所部分欄位名稱尾巴帶空白（例如 "主旨 "），先統一去掉
        row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
        if row.get("公司代號") != code or not row.get("主旨"):
            continue
        published = _roc_datetime(row.get("發言日期", ""), row.get("發言時間", ""))
        if published is None:
            continue
        subject = row["主旨"][:200]
        out.append(
            RawArticle(
                title=f"【重大訊息】{subject}",
                url=MOPS_URL,
                source="公開資訊觀測站",
                published_at=published,
                provider="twse",
                source_url=MOPS_URL,
                # 重大訊息沒有個別網址 → 用「代號 + 時間 + 主旨」當唯一鍵
                uid=f"twse:{code}:{row.get('發言日期')}:{row.get('發言時間')}:{subject[:40]}",
            )
        )
    return out


_twse_cache = TTLCache(ttl_seconds=10 * 60)  # 一次下載「全部」上市公司的公告，所有台股共用


def fetch_twse_announcements(symbol: str) -> list[RawArticle] | None:
    info = symbol_info(symbol)
    if not info.symbol.endswith(".TW"):
        return None  # 不適用：美股，或上櫃（.TWO，屬於櫃買中心，不在這個資料集）

    def download() -> list[dict]:
        resp = httpx.get(TWSE_ANNOUNCEMENTS_URL, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        return resp.json()

    return parse_twse_announcements(_twse_cache.get_or_set("all", download), info.code)


# ═════════════════════════════════════════════════════════════════════
# 4) Finnhub（美股，選用：需要免費 API Key）
# ═════════════════════════════════════════════════════════════════════
def parse_finnhub_news(items: list[dict]) -> list[RawArticle]:
    out: list[RawArticle] = []
    for it in items:
        title, url = (it.get("headline") or "").strip(), it.get("url")
        if not title or not _is_http(url) or not it.get("datetime"):
            continue
        published = datetime.fromtimestamp(int(it["datetime"]), tz=timezone.utc)
        out.append(RawArticle(title, url, it.get("source"), published, "finnhub", url))
    return out


def fetch_finnhub_news(symbol: str) -> list[RawArticle] | None:
    key = get_settings().finnhub_api_key
    if not key or symbol_info(symbol).market != "US":
        return None  # 不適用：沒設定 Key，或不是美股
    today = datetime.now(timezone.utc).date()
    resp = httpx.get(
        FINNHUB_NEWS_URL,
        params={"symbol": symbol, "from": str(today - timedelta(days=2)), "to": str(today)},
        # 用 Header 傳 Key，不放在網址上（網址常被記錄在 log 裡，容易外洩）
        headers={"X-Finnhub-Token": key, "User-Agent": USER_AGENT},
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    return parse_finnhub_news(resp.json())


# ═════════════════════════════════════════════════════════════════════
# Demo 新聞（離線開發用）
# ═════════════════════════════════════════════════════════════════════
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


def hash_int(s: str) -> int:
    return int(hashlib.md5(s.encode()).hexdigest()[:8], 16)


def fetch_demo_news(symbol: str) -> list[RawArticle]:
    info = symbol_info(symbol)
    name = CATALOG[symbol].name if symbol in CATALOG else info.code
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    rng = np.random.default_rng(int(now.timestamp() // 3600) ^ hash_int(symbol))
    templates = _DEMO_ZH if info.market == "TW" else _DEMO_EN
    picks = rng.choice(len(templates), size=4, replace=False)
    return [
        RawArticle(
            title=templates[i].format(n=name),
            url=f"https://example.com/demo-news/{info.code}/{now:%Y%m%d%H}/{i}",
            source="Demo News",
            published_at=now - timedelta(hours=int(rng.integers(0, 30))),
            provider="demo",
        )
        for i in picks
    ]


# ═════════════════════════════════════════════════════════════════════
# 合併所有來源
# ═════════════════════════════════════════════════════════════════════
PROVIDERS = {
    "yahoo": fetch_yahoo_news,
    "google": fetch_google_news,
    "twse": fetch_twse_announcements,
    "finnhub": fetch_finnhub_news,
}


def select_articles(articles: list[RawArticle], trusted_only: bool, now: datetime | None = None) -> list[RawArticle]:
    """過濾 → 統一來源名稱 → 跨來源去重複（保留等級最高的）→ 新到舊排序。"""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=MAX_AGE_HOURS)
    kept: dict[str, RawArticle] = {}
    for a in articles:
        if a.published_at < cutoff or not _is_http(a.url):
            continue
        trusted = classify_source(a.source, a.source_url or a.url)
        if trusted_only and trusted is None:
            continue
        if trusted:
            a.source = trusted.name  # "REUTERS"、"Reuters.com" → 統一成 "Reuters"
        k = title_key(a.title)
        best = kept.get(k)
        if best is None or TIER_RANK[a.tier] < TIER_RANK[best.tier]:
            kept[k] = a
    return sorted(kept.values(), key=lambda a: a.published_at, reverse=True)[:MAX_ARTICLES]


def fetch_news(symbol: str) -> list[RawArticle]:
    settings = get_settings()
    if settings.data_provider == "demo":
        return fetch_demo_news(symbol)

    enabled = {name: fn for name, fn in PROVIDERS.items() if name in settings.news_sources}
    results: list[RawArticle] = []
    attempted, failures = 0, []
    with ThreadPoolExecutor(max_workers=max(len(enabled), 1)) as pool:
        futures = {name: pool.submit(fn, symbol) for name, fn in enabled.items()}
        for name, fut in futures.items():
            try:
                got = fut.result()
            except Exception as exc:  # 單一來源失敗（逾時、被擋）不影響其他來源
                attempted += 1
                failures.append(f"{name}: {exc}")
                log.warning("news source %s failed for %s: %s", name, symbol, exc)
                continue
            if got is None:  # 這個來源不適用於這檔股票
                continue
            attempted += 1
            results.extend(got)
            log.info("news %s via %s: %d articles", symbol, name, len(got))

    if attempted and len(failures) == attempted:
        raise NewsUnavailableError("所有新聞來源都失敗：" + "；".join(failures))
    return select_articles(results, trusted_only=settings.news_trusted_only)
