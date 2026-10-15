"""
市場資料來源（Provider Pattern）。

用「介面 + 多種實作」的設計，好處是：
- YFinanceProvider：真實資料（美股 AAPL、台股 2330.TW 都支援）
- DemoProvider     ：離線假資料，沒網路 / Yahoo 被擋時也能開發與測試
之後要換 Fugle、Finnhub、Alpha Vantage，只要再寫一個 Provider 即可，其他程式完全不用改。
"""

import logging
import math
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol

import numpy as np
import pandas as pd

from ..config import get_settings
from .cache import TTLCache
from .symbols import symbol_info

log = logging.getLogger(__name__)

Interval = Literal["1d", "1wk"]


@dataclass
class Quote:
    symbol: str
    price: float
    prev_close: float
    change: float
    change_pct: float
    currency: str
    as_of: datetime


class MarketDataProvider(Protocol):
    def history(self, symbol: str, interval: Interval) -> pd.DataFrame: ...
    def quote(self, symbol: str) -> Quote: ...
    def fx_rate(self, from_ccy: str, to_ccy: str) -> float: ...
    def name(self, symbol: str) -> str | None: ...


def _make_quote(symbol: str, price: float, prev_close: float) -> Quote:
    change = price - prev_close
    return Quote(
        symbol=symbol,
        price=round(price, 4),
        prev_close=round(prev_close, 4),
        change=round(change, 4),
        change_pct=round(change / prev_close * 100, 3) if prev_close else 0.0,
        currency=symbol_info(symbol).currency,
        as_of=datetime.now(timezone.utc),
    )


# ═════════════════════════════════════════════════════════════════════
# 1) yfinance：真實行情
# ═════════════════════════════════════════════════════════════════════
class YFinanceProvider:
    # 日 K 抓 2 年（前面一段給 MA60 暖機），週 K 抓 5 年
    PERIODS: dict[str, str] = {"1d": "2y", "1wk": "5y"}

    def history(self, symbol: str, interval: Interval) -> pd.DataFrame:
        import yfinance as yf  # 延遲載入：Demo 模式不需要 yfinance 也能跑

        df = yf.Ticker(symbol).history(period=self.PERIODS[interval], interval=interval, auto_adjust=True)
        if df.empty:
            raise LookupError(f"找不到 {symbol} 的歷史資料（代碼錯誤或已下市？）")
        df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
        df.index = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
        return df.dropna(subset=["close"])

    def quote(self, symbol: str) -> Quote:
        import yfinance as yf

        t = yf.Ticker(symbol)
        try:
            fi = t.fast_info  # 比 .info 快很多，只拿價格相關欄位
            price, prev = float(fi.last_price), float(fi.previous_close)
            if math.isnan(price) or math.isnan(prev):
                raise ValueError("NaN quote")
        except Exception:  # fast_info 偶爾失敗 → 退回用最近 5 天日 K 推算
            hist = t.history(period="5d", interval="1d")
            if len(hist) < 2:
                raise LookupError(f"無法取得 {symbol} 報價")
            price, prev = float(hist["Close"].iloc[-1]), float(hist["Close"].iloc[-2])
        return _make_quote(symbol, price, prev)

    def fx_rate(self, from_ccy: str, to_ccy: str) -> float:
        import yfinance as yf

        if from_ccy == to_ccy:
            return 1.0
        return float(yf.Ticker(f"{from_ccy}{to_ccy}=X").fast_info.last_price)  # 例：USDTWD=X

    def name(self, symbol: str) -> str | None:
        import yfinance as yf

        try:
            info = yf.Ticker(symbol).info
            return info.get("shortName") or info.get("longName")
        except Exception:
            return None


# ═════════════════════════════════════════════════════════════════════
# 2) Demo：可重現的假資料（同一個代碼每次產生的走勢都一樣）
# ═════════════════════════════════════════════════════════════════════
_DEMO_BASE_PRICE: dict[str, float] = {
    "AAPL": 230, "NVDA": 180, "TSLA": 330, "MSFT": 510, "GOOGL": 240, "AMZN": 225, "META": 720,
    "2330.TW": 1350, "2454.TW": 1400, "2317.TW": 230, "2308.TW": 900, "2881.TW": 90, "0050.TW": 200,
}
_DEMO_FX = {("USD", "TWD"): 30.5, ("USD", "AUD"): 1.52, ("TWD", "AUD"): 0.0498}


class DemoProvider:
    BARS = 520  # 約 2 年交易日

    def _seed(self, symbol: str) -> int:
        return zlib.crc32(symbol.encode())  # 穩定的 hash（Python 內建 hash() 每次啟動都不同）

    def _daily(self, symbol: str) -> pd.DataFrame:
        rng = np.random.default_rng(self._seed(symbol))
        base = _DEMO_BASE_PRICE.get(symbol, float(rng.uniform(40, 400)))
        end = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
        dates = pd.bdate_range(end=end, periods=self.BARS)

        # 幾何布朗運動 + 慢速正弦「景氣循環」→ 走勢有漲有跌，指標比較有看頭
        drift = 0.0004 + 0.0025 * np.sin(np.linspace(0, 5 * np.pi, self.BARS) + rng.uniform(0, 6))
        rets = drift + rng.normal(0, 0.017, self.BARS)
        close = np.exp(np.cumsum(rets))
        close = close / close[-1] * base  # 讓最後收盤價落在 base 附近
        open_ = close * (1 + rng.normal(0, 0.006, self.BARS))
        spread = np.abs(rng.normal(0, 0.011, self.BARS))
        high = np.maximum(open_, close) * (1 + spread)
        low = np.minimum(open_, close) * (1 - spread)
        volume = rng.integers(5_000_000, 40_000_000, self.BARS).astype(float)
        return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=dates)

    def history(self, symbol: str, interval: Interval) -> pd.DataFrame:
        df = self._daily(symbol)
        if interval == "1wk":
            df = df.resample("W-FRI").agg(
                {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
            ).dropna()
        return df

    def quote(self, symbol: str) -> Quote:
        df = self._daily(symbol)
        # 以「目前小時」當種子做一點盤中跳動，讓畫面看得出每小時有更新
        hour_seed = self._seed(symbol) ^ int(datetime.now(timezone.utc).timestamp() // 3600)
        jitter = np.random.default_rng(hour_seed).normal(0, 0.004)
        return _make_quote(symbol, float(df["close"].iloc[-1]) * (1 + jitter), float(df["close"].iloc[-2]))

    def fx_rate(self, from_ccy: str, to_ccy: str) -> float:
        if from_ccy == to_ccy:
            return 1.0
        if (from_ccy, to_ccy) in _DEMO_FX:
            return _DEMO_FX[(from_ccy, to_ccy)]
        if (to_ccy, from_ccy) in _DEMO_FX:
            return 1 / _DEMO_FX[(to_ccy, from_ccy)]
        raise LookupError(f"Demo 模式沒有 {from_ccy}/{to_ccy} 匯率")

    def name(self, symbol: str) -> str | None:
        return None


# ═════════════════════════════════════════════════════════════════════
# 3) 對外介面：加上快取 + 平行抓取
# ═════════════════════════════════════════════════════════════════════
_history_cache = TTLCache(ttl_seconds=15 * 60)   # K 線 15 分鐘更新一次就夠
_quote_cache = TTLCache(ttl_seconds=60)          # 報價 1 分鐘
_fx_cache = TTLCache(ttl_seconds=60 * 60)        # 匯率 1 小時
_name_cache = TTLCache(ttl_seconds=24 * 3600)    # 公司名稱 1 天


def get_provider() -> MarketDataProvider:
    return DemoProvider() if get_settings().data_provider == "demo" else YFinanceProvider()


def get_history(symbol: str, interval: Interval = "1d") -> pd.DataFrame:
    return _history_cache.get_or_set((symbol, interval), lambda: get_provider().history(symbol, interval))


def get_quote(symbol: str) -> Quote:
    return _quote_cache.get_or_set(symbol, lambda: get_provider().quote(symbol))


def get_quotes(symbols: list[str]) -> dict[str, Quote | None]:
    """平行抓多檔報價（I/O bound 用 ThreadPool 很有效）。單檔失敗不影響其他檔。"""

    def safe(sym: str) -> Quote | None:
        try:
            return get_quote(sym)
        except Exception as exc:
            log.warning("quote failed for %s: %s", sym, exc)
            return None

    unique = list(dict.fromkeys(symbols))
    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(zip(unique, pool.map(safe, unique)))


def get_fx_rate(from_ccy: str, to_ccy: str) -> float:
    return _fx_cache.get_or_set((from_ccy, to_ccy), lambda: get_provider().fx_rate(from_ccy, to_ccy))


def get_name(symbol: str) -> str | None:
    return _name_cache.get_or_set(symbol, lambda: get_provider().name(symbol))
