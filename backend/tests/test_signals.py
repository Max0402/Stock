import numpy as np
import pytest

from app.services.indicators import add_indicators
from app.services.signals import (
    MARKER_COOLDOWN_BARS,
    InsufficientDataError,
    action_from_score,
    compute_signal,
    signal_markers,
)


def _uptrend_then_dip(n=200):
    """長期上漲，最後 8 天急跌 → 典型「多頭拉回」買點。"""
    rng = np.random.default_rng(42)
    base = np.linspace(100, 180, n) + rng.normal(0, 0.8, n)
    base[-8:] = base[-9] * np.linspace(0.985, 0.90, 8)
    return base


def _overheated(n=200):
    """盤整後最後 15 天連續急漲 → RSI 超買、突破上軌。"""
    rng = np.random.default_rng(7)
    base = 100 + rng.normal(0, 0.5, n)
    base[-15:] = base[-16] * np.cumprod(np.full(15, 1.025))
    return base


def test_levels_are_ordered(ohlcv):
    s = compute_signal(ohlcv(_uptrend_then_dip()))
    assert s.stop_loss < s.buy_zone_low < s.buy_zone_high < s.take_profit
    assert s.risk_reward >= 2 - 1e-9  # 設計上保證風報比 ≥ 2


def test_dip_in_uptrend_is_buy(ohlcv):
    s = compute_signal(ohlcv(_uptrend_then_dip()))
    assert s.action in ("BUY", "STRONG_BUY")
    assert s.rsi < 40
    assert any("RSI" in r for r in s.reasons)


def test_overheated_is_sell(ohlcv):
    s = compute_signal(ohlcv(_overheated()))
    assert s.action in ("SELL", "STRONG_SELL")
    assert s.rsi > 70 and s.percent_b > 0.8


def test_news_sentiment_moves_score(ohlcv):
    df = ohlcv(_uptrend_then_dip())
    neutral = compute_signal(df, None)
    bullish = compute_signal(df, 1.0)
    bearish = compute_signal(df, -1.0)
    assert bullish.score == pytest.approx(neutral.score + 2)
    assert bearish.score == pytest.approx(neutral.score - 2)
    assert compute_signal(df, 5.0).score == bullish.score  # 超出範圍會被夾到 ±1


def test_insufficient_data(ohlcv):
    with pytest.raises(InsufficientDataError):
        compute_signal(ohlcv(np.linspace(100, 110, 30)))


@pytest.mark.parametrize(
    "score, action", [(5, "STRONG_BUY"), (4, "STRONG_BUY"), (2, "BUY"), (1.9, "HOLD"), (0, "HOLD"),
                      (-2, "SELL"), (-4, "STRONG_SELL")],
)
def test_action_thresholds(score, action):
    assert action_from_score(score) == action


def test_markers_respect_cooldown(ohlcv):
    rng = np.random.default_rng(3)
    closes = 100 + 10 * np.sin(np.linspace(0, 12 * np.pi, 400)) + rng.normal(0, 0.5, 400)
    df = ohlcv(closes)
    markers = signal_markers(add_indicators(df))
    assert {m["type"] for m in markers} == {"BUY", "SELL"}
    pos = {ts.strftime("%Y-%m-%d"): i for i, ts in enumerate(df.index)}
    for kind in ("BUY", "SELL"):
        bars = [pos[m["time"]] for m in markers if m["type"] == kind]
        assert all(b - a >= MARKER_COOLDOWN_BARS for a, b in zip(bars, bars[1:]))
