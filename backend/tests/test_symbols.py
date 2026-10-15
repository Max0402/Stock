import pytest

from app.services.symbols import InvalidSymbolError, normalize_symbol, symbol_info


@pytest.mark.parametrize(
    "raw, expected",
    [("aapl", "AAPL"), (" 2330 ", "2330.TW"), ("2330.tw", "2330.TW"), ("6488.TWO", "6488.TWO"),
     ("00631L", "00631L.TW"), ("BRK-B", "BRK-B")],
)
def test_normalize(raw, expected):
    assert normalize_symbol(raw) == expected


@pytest.mark.parametrize("raw", ["", "AAPL; DROP TABLE", "../etc", "A" * 20, "<script>"])
def test_rejects_bad_symbols(raw):
    with pytest.raises(InvalidSymbolError):
        normalize_symbol(raw)


def test_market_detection():
    assert symbol_info("2330").market == "TW" and symbol_info("2330").currency == "TWD"
    assert symbol_info("NVDA").market == "US" and symbol_info("NVDA").currency == "USD"
