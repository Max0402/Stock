"""
技術指標計算（全部用 pandas 向量化運算，沒有 for 迴圈）。

輸入：DataFrame，欄位為 open / high / low / close / volume，index 是日期。
輸出：pandas Series（與輸入同長度，前面資料不足的部分是 NaN）。

指標說明
--------
- SMA（簡單移動平均）：過去 N 根 K 棒收盤價的平均。MA20 ≈ 月線、MA60 ≈ 季線。
- RSI（相對強弱指標，0~100）：近期漲幅 vs 跌幅的比例。
      > 70 超買（漲太多，可能拉回）、< 30 超賣（跌太多，可能反彈）。
- 布林通道（Bollinger Bands）：中軌 = MA20，上下軌 = 中軌 ± 2 倍標準差。
      統計上約 95% 的價格會落在上下軌之間，碰到下軌常被視為「便宜」。
- %B：目前價格在布林通道中的相對位置。0 = 下軌、0.5 = 中軌、1 = 上軌。
- ATR（平均真實波幅）：每天平均波動幾塊錢，用來設定「合理」的停損距離。
"""

import numpy as np
import pandas as pd


def sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(window=period, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI（業界標準算法，與 TradingView 相同）。"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder 平滑 = alpha 為 1/period 的指數移動平均
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    # 完全沒有下跌（avg_loss == 0）時 RSI 定義為 100
    out = out.where(avg_loss != 0, 100.0)
    return out.where(avg_gain.notna())


def bollinger(close: pd.Series, period: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = sma(close, period)
    std = close.rolling(window=period, min_periods=period).std(ddof=0)
    upper = mid + k * std
    lower = mid - k * std
    width = (upper - lower).replace(0, np.nan)
    return pd.DataFrame(
        {
            "bb_mid": mid,
            "bb_upper": upper,
            "bb_lower": lower,
            "percent_b": (close - lower) / width,
        }
    )


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """一次把所有指標加到 DataFrame 上（回傳新的 DataFrame，不修改原本的）。"""
    out = df.copy()
    close = out["close"]
    out["ma5"] = sma(close, 5)
    out["ma20"] = sma(close, 20)
    out["ma60"] = sma(close, 60)
    out["rsi"] = rsi(close, 14)
    out = out.join(bollinger(close, 20, 2.0))
    out["atr"] = atr(out, 14)
    # 吊燈停損（Chandelier Exit）用：過去 22 根 K 棒的最高價
    out["highest_22"] = out["high"].rolling(window=22, min_periods=22).max()
    return out
