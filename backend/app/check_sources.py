"""
連線診斷工具：逐一測試 Yahoo Finance 報價 / K 線，以及每個新聞來源。

用法（在 backend 資料夾）：
    python -m app.check_sources                 # 預設測 AAPL 和 2330.TW
    python -m app.check_sources NVDA 2454.TW

不論 .env 的 DATA_PROVIDER 設定為何，這裡一律測「真實」資料來源。
"""

import json
import logging
import sys
import time

from .config import get_settings
from .services.market_data import YFinanceProvider
from .services.news import PROVIDERS, relevance_terms, select_articles
from .services.symbols import normalize_symbol


def _timed(fn):
    start = time.monotonic()
    try:
        return fn(), None, time.monotonic() - start
    except Exception as exc:  # 診斷工具：把錯誤印出來，而不是中斷
        return None, f"{type(exc).__name__}: {exc}", time.monotonic() - start


def check(symbol: str) -> None:
    yf = YFinanceProvider()
    print(f"\n━━━ {symbol} ━━━")

    q, err, sec = _timed(lambda: yf.quote(symbol))
    print(f"  報價   {'✅' if q else '❌'} {f'{q.price} {q.currency}（漲跌 {q.change_pct:+.2f}%）' if q else err}  [{sec:.1f}s]")
    df, err, sec = _timed(lambda: yf.history(symbol, "1d"))
    print(f"  日K    {'✅' if df is not None else '❌'} {f'{len(df)} 根，最後一天 {df.index[-1]:%Y-%m-%d}' if df is not None else err}  [{sec:.1f}s]")

    settings = get_settings()
    terms = relevance_terms(symbol)
    print(f"  關鍵字 {terms}")
    for name, fn in PROVIDERS.items():
        if name not in settings.news_sources:
            print(f"  {name:<7}⏭️  未啟用（NEWS_SOURCES）")
            continue
        got, err, sec = _timed(lambda fn=fn: fn(symbol))
        if err:
            print(f"  {name:<7}❌ {err}  [{sec:.1f}s]")
        elif got is None:
            print(f"  {name:<7}⏭️  不適用於這檔股票（或未設定 API Key）")
        else:
            kept = select_articles(got, trusted_only=True, terms=terms)
            via = "（改用 Yahoo Search）" if got and got[0].provider == "yahoo_search" else ""
            print(f"  {name:<7}✅ 抓到 {len(got)} 則 → 可信且相關 {len(kept)} 則{via}  [{sec:.1f}s]")
            for a in kept[:3]:
                print(f"           · [{a.source}] {a.title[:70]}")
            if name == "yahoo" and not got:
                _debug_yahoo_raw(symbol)


def _debug_yahoo_raw(symbol: str) -> None:
    """Yahoo 回傳 0 則時：分別印出兩個 Yahoo 端點的原始資料，判斷是「Yahoo 沒給」還是「我們解析失敗」。"""
    import yfinance as yf

    def show(label, fetch):
        try:
            raw = fetch()
        except Exception as exc:
            print(f"           🔍 {label}：請求失敗 {type(exc).__name__}: {exc}")
            return
        print(f"           🔍 {label}：原始回傳 {len(raw)} 筆")
        if raw:
            print("           🔍 第一筆：" + json.dumps(raw[0], ensure_ascii=False, default=str)[:500])

    show("Ticker.get_news", lambda: yf.Ticker(symbol).get_news(count=5))
    show("Search.news", lambda: yf.Search(symbol, max_results=1, news_count=5, lists_count=0, include_cb=False).news)


def main(argv: list[str]) -> None:
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)  # 隱藏 yfinance 內部的重試訊息
    for raw in argv or ["AAPL", "2330.TW"]:
        check(normalize_symbol(raw))


if __name__ == "__main__":
    main(sys.argv[1:])
