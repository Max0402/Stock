"""確保診斷指令真的會印出結果（曾經因為 __main__ 區塊被誤刪而「什麼都不印」）。"""

import subprocess
import sys
from pathlib import Path

from app import check_sources
from app.services import news
from app.services.market_data import YFinanceProvider, _make_quote

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_module_has_entry_point():
    src = (BACKEND_DIR / "app" / "check_sources.py").read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in src


def test_check_prints_every_section(monkeypatch, capsys):
    import pandas as pd

    monkeypatch.setattr(YFinanceProvider, "quote", lambda self, s: _make_quote(s, 101.0, 100.0))
    monkeypatch.setattr(
        YFinanceProvider, "history",
        lambda self, s, i: pd.DataFrame({"close": [1.0]}, index=pd.DatetimeIndex(["2026-10-15"])),
    )
    monkeypatch.setattr(news, "PROVIDERS", {"yahoo": lambda s: [], "google": lambda s: [], "twse": lambda s: None,
                                            "finnhub": lambda s: None})
    monkeypatch.setattr(check_sources, "PROVIDERS", news.PROVIDERS)
    monkeypatch.setattr(check_sources, "_debug_yahoo_raw", lambda s: print("           🔍 debug"))

    check_sources.main(["AAPL"])
    out = capsys.readouterr().out
    for expected in ("AAPL", "報價", "日K", "關鍵字", "yahoo", "google", "🔍 debug"):
        assert expected in out


def test_runs_as_module_and_prints():
    # 真的用 `python -m app.check_sources` 執行（不連網：無效代碼會在驗證階段就報錯，但至少要有輸出）
    proc = subprocess.run(
        [sys.executable, "-m", "app.check_sources", "bad$$"],
        cwd=BACKEND_DIR, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode != 0 and "格式不正確" in (proc.stdout + proc.stderr)
