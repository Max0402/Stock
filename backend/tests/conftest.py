"""
測試設定：一律用 Demo 資料 + 暫存 SQLite，不連網、不碰正式資料庫。
注意：環境變數必須在 import app 之前設定（Settings 與 engine 在 import 時就建立）。
"""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="stock-test-")
os.environ.update(
    {
        "DATA_PROVIDER": "demo",
        "ENABLE_SCHEDULER": "false",
        "CRON_SECRET": "test-secret",
        "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
        "ANTHROPIC_API_KEY": "",
    }
)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402


def make_ohlcv(closes) -> pd.DataFrame:
    """用收盤價序列造出一份合理的 OHLCV（high/low 在收盤上下 1%）。"""
    closes = np.asarray(closes, dtype=float)
    idx = pd.bdate_range("2024-01-01", periods=len(closes))
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes * 1.01,
            "low": closes * 0.99,
            "close": closes,
            "volume": np.full(len(closes), 1_000_000.0),
        },
        index=idx,
    )


@pytest.fixture
def ohlcv():
    return make_ohlcv
