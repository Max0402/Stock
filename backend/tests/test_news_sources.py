"""新聞多來源：解析、白名單、去重複（全部用假資料，不連網）。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.config import get_settings
from app.services import news
from app.services.news import (
    NewsUnavailableError,
    RawArticle,
    google_news_rss_url,
    parse_finnhub_news,
    parse_google_rss,
    parse_twse_announcements,
    parse_yahoo_news,
    select_articles,
    title_key,
)
from app.services.news_sources import classify_source, google_site_filter, tier_of

NOW = datetime.now(timezone.utc)


# ── 白名單 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "name, url, expected",
    [
        ("Reuters", None, "Reuters"),
        ("REUTERS", None, "Reuters"),
        (None, "https://www.reuters.com/markets/x", "Reuters"),
        ("經濟日報", None, "經濟日報"),
        (None, "https://money.udn.com/money/story/1", "經濟日報"),
        ("Barron’s", None, "Barron's"),  # 彎引號也能比對
        ("公開資訊觀測站", None, "公開資訊觀測站"),
    ],
)
def test_classify_trusted(name, url, expected):
    assert classify_source(name, url).name == expected


@pytest.mark.parametrize(
    "name, url",
    [("Some Content Farm", "https://best-stock-tips.example"), (None, "https://evilreuters.com/x"), (None, None)],
)
def test_classify_untrusted(name, url):
    assert classify_source(name, url) is None  # evilreuters.com 不能被當成 reuters.com


def test_tiers():
    assert tier_of("公開資訊觀測站") == "official"
    assert tier_of("Bloomberg") == "major"
    assert tier_of("Business Wire") == "press_release"
    assert tier_of("Motley Fool") == "other"


def test_google_site_filter_is_market_specific():
    us, tw = google_site_filter("US"), google_site_filter("TW")
    assert "site:reuters.com" in us and "cnyes.com" not in us
    assert "site:money.udn.com" in tw and "reuters.com" not in tw
    url = google_news_rss_url("2330.TW")
    assert "hl=zh-TW" in url and "site%3Acna.com.tw" in url


# ── Yahoo Finance ─────────────────────────────────────────────────
def test_parse_yahoo_new_and_legacy_formats():
    items = [
        {  # yfinance 新版格式
            "id": "1",
            "content": {
                "contentType": "STORY",
                "title": "Nvidia beats estimates",
                "pubDate": "2026-10-15T12:00:00Z",
                "provider": {"displayName": "Reuters", "url": "https://www.reuters.com"},
                "canonicalUrl": {"url": "https://finance.yahoo.com/news/nvidia-1.html"},
                "clickThroughUrl": None,
            },
        },
        {"id": "2", "content": {"contentType": "VIDEO", "title": "video", "pubDate": "2026-10-15T12:00:00Z"}},
        {  # 舊版格式
            "title": "Apple raises guidance",
            "link": "https://finance.yahoo.com/news/apple-2.html",
            "publisher": "Bloomberg",
            "providerPublishTime": 1760529600,
        },
        {"content": {"title": "bad link", "pubDate": "2026-10-15T12:00:00Z", "canonicalUrl": {"url": "javascript:alert(1)"}}},
    ]
    out = parse_yahoo_news(items)
    assert [a.title for a in out] == ["Nvidia beats estimates", "Apple raises guidance"]
    assert out[0].source == "Reuters" and out[0].provider == "yahoo"
    assert out[0].published_at == datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
    assert out[1].source == "Bloomberg"


# ── Google News RSS ───────────────────────────────────────────────
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>TSMC revenue jumps - Reuters</title><link>https://news.google.com/rss/articles/a1</link>
<pubDate>Thu, 15 Oct 2026 10:00:00 GMT</pubDate><source url="https://www.reuters.com">Reuters</source></item>
<item><title>Stock to buy now!!! - Penny Picks</title><link>https://news.google.com/rss/articles/a2</link>
<pubDate>Thu, 15 Oct 2026 11:00:00 GMT</pubDate><source url="https://pennypicks.example">Penny Picks</source></item>
</channel></rss>"""


def test_parse_google_rss():
    out = parse_google_rss(RSS)
    assert out[0].title == "TSMC revenue jumps"  # 去掉「 - Reuters」
    assert out[0].source_url == "https://www.reuters.com"
    assert out[0].tier == "major" and out[1].tier == "other"


# ── 證交所重大訊息 ─────────────────────────────────────────────────
def test_parse_twse_announcements():
    rows = [
        {"出表日期": "1151016", "發言日期": "1151016", "發言時間": "143005", "公司代號": "2330",
         "公司名稱": "台積電", "主旨 ": "本公司董事會決議股利分派", "符合條款": "第14款"},
        {"發言日期": "1151016", "發言時間": "90000", "公司代號": "2317", "主旨 ": "鴻海公告"},
        {"發言日期": "bad", "發言時間": "1", "公司代號": "2330", "主旨 ": "格式錯誤的資料會被略過"},
    ]
    out = parse_twse_announcements(rows, "2330")
    assert len(out) == 1
    a = out[0]
    assert a.title == "【重大訊息】本公司董事會決議股利分派"
    # 民國 115 年 = 2026 年；台北 14:30:05 = UTC 06:30:05
    assert a.published_at == datetime(2026, 10, 16, 6, 30, 5, tzinfo=timezone.utc)
    assert a.tier == "official" and a.uid.startswith("twse:2330:")


# ── Finnhub ───────────────────────────────────────────────────────
def test_parse_finnhub():
    items = [
        {"headline": "Apple upgrade", "url": "https://www.cnbc.com/a", "source": "CNBC", "datetime": 1760529600},
        {"headline": "", "url": "https://x", "datetime": 1},
    ]
    out = parse_finnhub_news(items)
    assert len(out) == 1 and out[0].source == "CNBC" and out[0].provider == "finnhub"


# ── 合併 / 過濾 / 去重複 ───────────────────────────────────────────
def _a(title, source, hours_ago=1, url=None, provider="google"):
    return RawArticle(title, url or f"https://x.example/{title_key(title)}/{source}", source,
                      NOW - timedelta(hours=hours_ago), provider)


def test_select_filters_untrusted_old_and_dedupes():
    arts = [
        _a("Nvidia beats estimates!", "Business Wire", 1),
        _a("Nvidia Beats Estimates", "Reuters", 2),        # 同一則新聞 → 保留等級較高的 Reuters
        _a("Buy this stock now", "Penny Picks", 1),         # 不在白名單 → 移除
        _a("Old Reuters story", "Reuters", 72),             # 超過 48 小時 → 移除
        _a("CNBC fresh", "CNBC", 0.5),
    ]
    out = select_articles(arts, trusted_only=True, now=NOW)
    assert [(a.title, a.source) for a in out] == [("CNBC fresh", "CNBC"), ("Nvidia Beats Estimates", "Reuters")]
    loose = select_articles(arts, trusted_only=False, now=NOW)
    assert any(a.source == "Penny Picks" for a in loose)


def _live_settings(monkeypatch, **overrides):
    s = get_settings().model_copy(update={"data_provider": "yfinance", **overrides})
    monkeypatch.setattr(news, "get_settings", lambda: s)


def test_fetch_news_survives_one_failing_source(monkeypatch):
    _live_settings(monkeypatch, news_sources=["yahoo", "google", "twse"])

    def boom(symbol):
        raise TimeoutError("timeout")

    monkeypatch.setattr(news, "PROVIDERS", {
        "yahoo": boom,
        "google": lambda s: [_a("Reuters says AAPL up", "Reuters")],
        "twse": lambda s: None,  # 美股不適用
    })
    out = news.fetch_news("AAPL")
    assert [a.source for a in out] == ["Reuters"]


def test_fetch_news_all_sources_failing_raises(monkeypatch):
    _live_settings(monkeypatch, news_sources=["yahoo", "google", "twse"])

    def boom(symbol):
        raise ConnectionError("blocked")

    monkeypatch.setattr(news, "PROVIDERS", {"yahoo": boom, "google": boom, "twse": lambda s: None})
    with pytest.raises(NewsUnavailableError):
        news.fetch_news("AAPL")


def test_finnhub_skipped_without_key_or_for_tw(monkeypatch):
    _live_settings(monkeypatch, finnhub_api_key=None)
    assert news.fetch_finnhub_news("AAPL") is None
    _live_settings(monkeypatch, finnhub_api_key="k")
    assert news.fetch_finnhub_news("2330.TW") is None
    assert news.fetch_twse_announcements("AAPL") is None
