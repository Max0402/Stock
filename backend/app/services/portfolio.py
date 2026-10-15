"""
投資組合損益計算（純函式，沒有 I/O → 很好寫單元測試）。

公式（以單一持股、原幣別計）
----------------------------
    總市值        market_value       = 股數 × 現價
    成本          cost_basis         = 股數 × 平均成本
    未實現損益    unrealized_pnl     = 市值 − 成本
    報酬率        unrealized_pnl_pct = 未實現損益 / 成本 × 100%
    今日損益      day_pnl            = 股數 × (現價 − 昨收)

整個投資組合：每檔先乘上匯率換成 base currency（例如 TWD）再加總。
    今日損益 %    day_pnl_pct        = 今日損益 / 昨日市值 × 100%
                                        （昨日市值 = 今日市值 − 今日損益）
"""

from dataclasses import dataclass


@dataclass
class PositionMetrics:
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    day_pnl: float


@dataclass
class PortfolioTotals:
    market_value: float = 0.0
    cost_basis: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    day_pnl: float = 0.0
    day_pnl_pct: float = 0.0


def position_metrics(shares: float, avg_cost: float, price: float, prev_close: float) -> PositionMetrics:
    market_value = shares * price
    cost_basis = shares * avg_cost
    pnl = market_value - cost_basis
    return PositionMetrics(
        market_value=round(market_value, 4),
        cost_basis=round(cost_basis, 4),
        unrealized_pnl=round(pnl, 4),
        unrealized_pnl_pct=round(pnl / cost_basis * 100, 3) if cost_basis else 0.0,
        day_pnl=round(shares * (price - prev_close), 4),
    )


def aggregate(positions: list[tuple[PositionMetrics, float]]) -> PortfolioTotals:
    """
    positions：[(單檔指標, 換算成 base currency 的匯率), ...]
    沒有報價的持股請不要傳進來（市值未知時，成本也不列入，避免報酬率失真）。
    """
    t = PortfolioTotals()
    for m, fx in positions:
        t.market_value += m.market_value * fx
        t.cost_basis += m.cost_basis * fx
        t.day_pnl += m.day_pnl * fx
    t.unrealized_pnl = t.market_value - t.cost_basis
    t.unrealized_pnl_pct = t.unrealized_pnl / t.cost_basis * 100 if t.cost_basis else 0.0
    prev_value = t.market_value - t.day_pnl
    t.day_pnl_pct = t.day_pnl / prev_value * 100 if prev_value else 0.0
    return PortfolioTotals(**{k: round(v, 3) for k, v in vars(t).items()})
