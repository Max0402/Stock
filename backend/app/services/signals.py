"""
買賣訊號演算法：RSI + 布林通道 + 均線趨勢 + 新聞情緒。

═══════════════════════════════════════════════════════════════════
一、價位計算（Buy Zone / Take Profit / Stop Loss）
═══════════════════════════════════════════════════════════════════
    buy_zone_high = (布林下軌 + 中軌) / 2         ← 價格回到通道「下半部」才考慮買
    buy_zone_low  = 布林下軌 − 0.5 × ATR          ← 容許稍微跌破下軌（常見的假跌破）
    entry_ref     = 買進區中點                      ← 用來計算風報比的參考進場價
    stop_loss     = buy_zone_low − 1 × ATR        ← 再多留一天的平均波動當緩衝
    take_profit   = max(布林上軌, entry_ref + 2 × 風險)  ← 目標至少是風險的 2 倍（風報比 ≥ 2:1）
    trailing_stop = 近 22 根最高價 − 3 × ATR       ← 吊燈停損（Chandelier Exit），給「已持有」的人用

    為什麼用 ATR？
    固定 -5% 停損對台積電和特斯拉意義完全不同（波動度差很多）。
    ATR 讓停損距離跟著「這檔股票平常的波動」自動調整。

═══════════════════════════════════════════════════════════════════
二、訊號分數（Score）
═══════════════════════════════════════════════════════════════════
    RSI      < 30: +2（超賣）   < 40: +1   > 60: −1   > 70: −2（超買）
    %B       < 0 : +2（跌破下軌）< 0.2: +1  > 0.8: −1  > 1 : −2（突破上軌）
    趨勢      收盤 > MA60 且 MA20 > MA60（多頭排列）: +1；反之空頭排列: −1
    新聞情緒  sentiment(−1~+1) × 2  → −2 ~ +2

    總分 ≥ 4 強力買進｜≥ 2 買進｜≤ −2 賣出｜≤ −4 強力賣出｜其餘 觀望

    設計理念：「多頭趨勢中的拉回」是勝率較高的買點（RSI/%B 低 + 趨勢向上 → 分數高），
    「漲過頭」時提醒停利（RSI/%B 高 → 分數低）。

⚠️ 這是教學用的簡化模型，不構成投資建議。實際使用前請先做回測（Backtest）。
"""

from dataclasses import asdict, dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from .indicators import add_indicators

Action = Literal["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"]

MIN_BARS = 60          # MA60 需要至少 60 根 K 棒
BUY_THRESHOLD = 2
STRONG_THRESHOLD = 4
NEWS_WEIGHT = 2.0
MARKER_COOLDOWN_BARS = 5  # 同方向訊號至少間隔 5 根 K 棒，避免圖上密密麻麻


class InsufficientDataError(ValueError):
    pass


@dataclass
class TradeSignal:
    action: Action
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
    zone_status: Literal["BELOW", "IN", "ABOVE"]  # 現價相對於買進區的位置
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────
# 向量化的技術面分數（整段歷史一次算完，K 線圖上的買賣標記也用它）
# ─────────────────────────────────────────────────────────────────────
def technical_score_series(ind: pd.DataFrame) -> pd.Series:
    r, pb = ind["rsi"], ind["percent_b"]
    close, ma20, ma60 = ind["close"], ind["ma20"], ind["ma60"]

    # np.select：依序檢查條件，第一個成立的就套用對應分數（類似 if/elif）
    rsi_pts = np.select([r < 30, r < 40, r > 70, r > 60], [2, 1, -2, -1], default=0)
    pb_pts = np.select([pb < 0, pb < 0.2, pb > 1, pb > 0.8], [2, 1, -2, -1], default=0)
    up = (close > ma60) & (ma20 > ma60)
    down = (close < ma60) & (ma20 < ma60)
    trend_pts = np.where(up, 1, np.where(down, -1, 0))

    score = pd.Series(rsi_pts + pb_pts + trend_pts, index=ind.index, dtype=float)
    valid = r.notna() & pb.notna() & ma60.notna()
    return score.where(valid)


def action_from_score(score: float) -> Action:
    if score >= STRONG_THRESHOLD:
        return "STRONG_BUY"
    if score >= BUY_THRESHOLD:
        return "BUY"
    if score <= -STRONG_THRESHOLD:
        return "STRONG_SELL"
    if score <= -BUY_THRESHOLD:
        return "SELL"
    return "HOLD"


def _reasons(row: pd.Series, trend: str, news_score: float | None) -> list[str]:
    """把分數拆成人看得懂的理由，顯示在 UI 的 tooltip。"""
    out: list[str] = []
    r, pb = row["rsi"], row["percent_b"]
    if r < 30:
        out.append(f"RSI {r:.0f} 進入超賣區（< 30）")
    elif r < 40:
        out.append(f"RSI {r:.0f} 偏弱，接近超賣")
    elif r > 70:
        out.append(f"RSI {r:.0f} 進入超買區（> 70）")
    elif r > 60:
        out.append(f"RSI {r:.0f} 偏強，留意過熱")

    if pb < 0:
        out.append("收盤價跌破布林下軌")
    elif pb < 0.2:
        out.append("價格接近布林下軌")
    elif pb > 1:
        out.append("收盤價突破布林上軌（短線過熱）")
    elif pb > 0.8:
        out.append("價格接近布林上軌")

    if trend == "UP":
        out.append("均線多頭排列（收盤 > MA60 且 MA20 > MA60）")
    elif trend == "DOWN":
        out.append("均線空頭排列（收盤 < MA60 且 MA20 < MA60）")

    if news_score is not None:
        if news_score > 0.15:
            out.append(f"新聞情緒偏多（{news_score:+.2f}）")
        elif news_score < -0.15:
            out.append(f"新聞情緒偏空（{news_score:+.2f}）")
        else:
            out.append("新聞情緒中性")
    return out


def compute_signal(df: pd.DataFrame, news_score: float | None = None) -> TradeSignal:
    """
    df：OHLCV 歷史資料（日 K 或週 K 都可以）
    news_score：最近新聞的情緒分數（-1 ~ +1），沒有新聞就傳 None
    """
    if len(df) < MIN_BARS:
        raise InsufficientDataError(f"需要至少 {MIN_BARS} 根 K 棒，目前只有 {len(df)} 根")

    ind = add_indicators(df)
    tech = technical_score_series(ind)
    row = ind.iloc[-1]
    tech_score = float(tech.iloc[-1])

    close = float(row["close"])
    lower, mid, upper = float(row["bb_lower"]), float(row["bb_mid"]), float(row["bb_upper"])
    atr_v = float(row["atr"])

    # ── 價位 ─────────────────────────────────────────────
    zone_high = (lower + mid) / 2
    zone_low = lower - 0.5 * atr_v
    entry_ref = (zone_low + zone_high) / 2
    stop_loss = zone_low - 1.0 * atr_v
    risk = max(entry_ref - stop_loss, 1e-9)
    take_profit = max(upper, entry_ref + 2 * risk)
    risk_reward = (take_profit - entry_ref) / risk
    trailing_stop = float(row["highest_22"]) - 3 * atr_v

    if close < zone_low:
        zone_status = "BELOW"
    elif close <= zone_high:
        zone_status = "IN"
    else:
        zone_status = "ABOVE"

    # ── 趨勢 ─────────────────────────────────────────────
    if close > row["ma60"] and row["ma20"] > row["ma60"]:
        trend = "UP"
    elif close < row["ma60"] and row["ma20"] < row["ma60"]:
        trend = "DOWN"
    else:
        trend = "SIDEWAYS"

    # ── 總分 ─────────────────────────────────────────────
    news_pts = 0.0 if news_score is None else float(np.clip(news_score, -1, 1)) * NEWS_WEIGHT
    total = tech_score + news_pts

    reasons = _reasons(row, trend, news_score)
    if close <= trailing_stop:
        reasons.append("收盤價已跌破移動停損，持有者請留意風險")

    return TradeSignal(
        action=action_from_score(total),
        score=round(total, 2),
        technical_score=tech_score,
        news_score=None if news_score is None else round(float(news_score), 3),
        price=round(close, 4),
        rsi=round(float(row["rsi"]), 2),
        percent_b=round(float(row["percent_b"]), 3),
        trend=trend,
        buy_zone_low=round(zone_low, 2),
        buy_zone_high=round(zone_high, 2),
        take_profit=round(take_profit, 2),
        stop_loss=round(stop_loss, 2),
        trailing_stop=round(trailing_stop, 2),
        risk_reward=round(risk_reward, 2),
        zone_status=zone_status,
        reasons=reasons,
    )


def signal_markers(ind: pd.DataFrame) -> list[dict]:
    """
    找出歷史上「技術面分數穿越門檻」的時間點，在 K 線圖上畫 ▲ / ▼。
    - 分數由 < 2 變成 ≥ 2  → BUY 標記
    - 分數由 > -2 變成 ≤ -2 → SELL 標記
    （只用技術面，因為歷史新聞情緒資料不一定齊全）
    """
    score = technical_score_series(ind)
    prev = score.shift(1)
    buy_cross = (score >= BUY_THRESHOLD) & (prev < BUY_THRESHOLD)
    sell_cross = (score <= -BUY_THRESHOLD) & (prev > -BUY_THRESHOLD)

    markers: list[dict] = []
    last_idx = {"BUY": -10**9, "SELL": -10**9}
    for i, (ts, is_buy, is_sell) in enumerate(zip(ind.index, buy_cross, sell_cross)):
        kind = "BUY" if is_buy else "SELL" if is_sell else None
        if kind is None or i - last_idx[kind] < MARKER_COOLDOWN_BARS:
            continue
        last_idx[kind] = i
        markers.append(
            {
                "time": ts.strftime("%Y-%m-%d"),
                "type": kind,
                "price": round(float(ind["close"].iloc[i]), 4),
                "score": float(score.iloc[i]),
            }
        )
    return markers
