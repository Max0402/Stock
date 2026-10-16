"""
連線診斷工具：逐一測試 Yahoo Finance 報價 / K 線，以及每個新聞來源。

用法（在 backend 資料夾）：
    python -m app.check_sources                 # 預設測 AAPL 和 2330.TW
    python -m app.check_sources NVDA 2454.TW

不論 .env 的 DATA_PROVIDER 設定為何，這裡一律測「真實」資料來源。
"""

import logging
import sys
import time

from .config import get_settings
from .services.market_data import YFinanceProvider
from .services.news import PROVIDERS, select_articles
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
            trusted = select_articles(got, trusted_only=True)
            print(f"  {name:<7}✅ 抓到 {len(got)} 則，可信來源 {len(trusted)} 則  [{sec:.1f}s]")
            for a in trusted[:3]:
                print(f"           · [{a.source}] {a.title[:70]}")


if __name__ == "__main__":
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)  # 隱藏 yfinance 內部的重試訊息
    for raw in sys.argv[1:] or ["AAPL", "2330.TW"]:
        check(normalize_symbol(raw))
