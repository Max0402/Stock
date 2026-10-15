import numpy as np
import pandas as pd

from app.services.indicators import add_indicators, atr, bollinger, rsi, sma


def test_sma_basic():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = sma(s, 3)
    assert out.isna().sum() == 2
    assert out.iloc[-1] == 4.0


def test_rsi_extremes_and_bounds():
    up = pd.Series(np.arange(1, 50, dtype=float))
    assert rsi(up).iloc[-1] == 100.0  # 只漲不跌 → 100
    down = pd.Series(np.arange(50, 1, -1, dtype=float))
    assert rsi(down).iloc[-1] < 1  # 只跌不漲 → 接近 0
    noisy = pd.Series(100 + np.random.default_rng(0).normal(0, 1, 300).cumsum())
    r = rsi(noisy).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_bollinger_mid_is_sma_and_percent_b():
    s = pd.Series(100 + np.random.default_rng(1).normal(0, 2, 100))
    bb = bollinger(s)
    pd.testing.assert_series_equal(bb["bb_mid"], sma(s, 20), check_names=False)
    assert (bb["bb_upper"].dropna() > bb["bb_lower"].dropna()).all()
    # %B = 0.5 代表剛好在中軌
    i = 50
    expected = (s[i] - bb["bb_lower"][i]) / (bb["bb_upper"][i] - bb["bb_lower"][i])
    assert abs(bb["percent_b"][i] - expected) < 1e-12


def test_atr_positive(ohlcv):
    df = ohlcv(100 + np.random.default_rng(2).normal(0, 1, 100).cumsum())
    assert (atr(df).dropna() > 0).all()


def test_add_indicators_columns(ohlcv):
    df = ohlcv(np.linspace(100, 200, 120))
    out = add_indicators(df)
    for col in ["ma5", "ma20", "ma60", "rsi", "bb_upper", "bb_mid", "bb_lower", "percent_b", "atr", "highest_22"]:
        assert col in out
    assert "ma5" not in df  # 不修改原始 DataFrame
