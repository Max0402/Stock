"""
股票代碼的正規化與驗證。

為什麼要做這件事？
1. 使用者可能輸入 "2330"、" aapl "、"2330.tw"，要統一成 "2330.TW"、"AAPL"。
2. 代碼會被拼進外部 API 的 URL —— 先用白名單 Regex 驗證，避免奇怪字元（資安：輸入驗證）。
"""

import re
from dataclasses import dataclass

# 只允許英數字、點、橫線，長度 1~15。例：AAPL、BRK-B、2330.TW、6488.TWO
_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")
# 純數字（可帶一個英文字母，如 00631L）→ 視為台股上市代碼
_TW_CODE_RE = re.compile(r"^\d{4,6}[A-Z]?$")


class InvalidSymbolError(ValueError):
    pass


@dataclass(frozen=True)
class SymbolInfo:
    symbol: str     # 正規化後的代碼（yfinance 格式）
    market: str     # "US" | "TW"
    currency: str   # "USD" | "TWD"
    code: str       # 不含市場後綴的代碼，例："2330"、"AAPL"


def normalize_symbol(raw: str) -> str:
    s = raw.strip().upper()
    if _TW_CODE_RE.match(s):
        # 使用者只輸入 "2330" → 預設上市（.TW）。上櫃股票請自行輸入 ".TWO"
        s = f"{s}.TW"
    if not _SYMBOL_RE.match(s):
        raise InvalidSymbolError(f"股票代碼格式不正確：{raw!r}")
    return s


def symbol_info(raw: str) -> SymbolInfo:
    s = normalize_symbol(raw)
    if s.endswith(".TW") or s.endswith(".TWO"):
        return SymbolInfo(symbol=s, market="TW", currency="TWD", code=s.split(".")[0])
    return SymbolInfo(symbol=s, market="US", currency="USD", code=s)
