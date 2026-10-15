import pytest

from app.services.portfolio import aggregate, position_metrics


def test_position_metrics():
    m = position_metrics(shares=10, avg_cost=100, price=120, prev_close=115)
    assert m.market_value == 1200
    assert m.cost_basis == 1000
    assert m.unrealized_pnl == 200
    assert m.unrealized_pnl_pct == 20
    assert m.day_pnl == 50


def test_aggregate_with_fx():
    us = position_metrics(10, 100, 110, 100)      # USD：市值 1100，今日 +100
    tw = position_metrics(1000, 500, 600, 590)    # TWD：市值 600000，今日 +10000
    t = aggregate([(us, 30.0), (tw, 1.0)])        # 換算成 TWD
    assert t.market_value == pytest.approx(1100 * 30 + 600000)
    assert t.cost_basis == pytest.approx(1000 * 30 + 500000)
    assert t.unrealized_pnl == pytest.approx(t.market_value - t.cost_basis)
    assert t.day_pnl == pytest.approx(100 * 30 + 10000)
    assert t.day_pnl_pct == pytest.approx(t.day_pnl / (t.market_value - t.day_pnl) * 100, rel=1e-3)


def test_empty_portfolio():
    t = aggregate([])
    assert t.market_value == 0 and t.unrealized_pnl_pct == 0 and t.day_pnl_pct == 0
