"""
持股管理 API。

GET    /api/portfolio           取得投資組合（含即時報價、損益、訊號、新聞情緒）
POST   /api/holdings            新增持股
PATCH  /api/holdings/{id}       修改持股（股數 / 成本 / 備註）
DELETE /api/holdings/{id}       刪除持股
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import get_current_user, get_portfolio
from ..models import Holding, Portfolio, User, WatchlistItem
from ..schemas import HoldingIn, HoldingOut, HoldingUpdate, PortfolioOut, PortfolioSummaryOut
from ..services.analysis import analyze_symbols, quote_out, sentiment_out, signal_out
from ..services.market_data import get_fx_rate, get_quote
from ..services.portfolio import aggregate, position_metrics
from ..services.symbols import symbol_info

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["portfolio"])


def _owned_holding(db: Session, portfolio: Portfolio, holding_id: int) -> Holding:
    # 一定要同時比對 portfolio_id：否則使用者改網址的 id 就能動到別人的持股（IDOR）
    h = db.scalar(select(Holding).where(Holding.id == holding_id, Holding.portfolio_id == portfolio.id))
    if h is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到這筆持股")
    return h


@router.get("/portfolio", response_model=PortfolioOut)
def read_portfolio(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    portfolio: Portfolio = Depends(get_portfolio),
):
    base = user.base_currency or get_settings().base_currency
    holdings = list(db.scalars(select(Holding).where(Holding.portfolio_id == portfolio.id).order_by(Holding.id)))
    starred = set(db.scalars(select(WatchlistItem.symbol).where(WatchlistItem.user_id == user.id)))
    analyses = analyze_symbols(db, [h.symbol for h in holdings])

    fx_rates: dict[str, float] = {}
    for ccy in {h.currency for h in holdings} | {base}:
        try:
            fx_rates[ccy] = get_fx_rate(ccy, base)
        except Exception as exc:
            log.warning("fx %s->%s failed: %s", ccy, base, exc)

    out: list[HoldingOut] = []
    priced: list = []
    for h in holdings:
        a = analyses[h.symbol]
        m = position_metrics(h.shares, h.avg_cost, a.quote.price, a.quote.prev_close) if a.quote else None
        if m is not None and h.currency in fx_rates:
            priced.append((m, fx_rates[h.currency]))
        out.append(
            HoldingOut(
                id=h.id, symbol=h.symbol, name=a.name, market=h.market, currency=h.currency,
                shares=h.shares, buy_price=h.buy_price, avg_cost=h.avg_cost, note=h.note,
                quote=quote_out(a.quote),
                market_value=m.market_value if m else None,
                cost_basis=round(h.shares * h.avg_cost, 4),
                unrealized_pnl=m.unrealized_pnl if m else None,
                unrealized_pnl_pct=m.unrealized_pnl_pct if m else None,
                day_pnl=m.day_pnl if m else None,
                signal=signal_out(a.signal), sentiment=sentiment_out(a.digest),
                starred=h.symbol in starred,
            )
        )

    totals = aggregate(priced)
    return PortfolioOut(
        summary=PortfolioSummaryOut(base_currency=base, fx_rates=fx_rates, **vars(totals)),
        holdings=out,
        updated_at=datetime.now(timezone.utc),
    )


@router.post("/holdings", status_code=status.HTTP_201_CREATED)
def create_holding(body: HoldingIn, db: Session = Depends(get_db), portfolio: Portfolio = Depends(get_portfolio)):
    exists = db.scalar(select(Holding).where(Holding.portfolio_id == portfolio.id, Holding.symbol == body.symbol))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.symbol} 已在持股中，請直接編輯")
    try:
        get_quote(body.symbol)  # 順便驗證代碼真的存在
    except Exception:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"查無 {body.symbol} 的報價，請確認代碼") from None

    info = symbol_info(body.symbol)
    h = Holding(
        portfolio_id=portfolio.id, symbol=info.symbol, market=info.market, currency=info.currency,
        shares=body.shares, buy_price=body.buy_price, avg_cost=body.avg_cost or body.buy_price, note=body.note,
    )
    db.add(h)
    db.commit()
    return {"id": h.id, "symbol": h.symbol}


@router.patch("/holdings/{holding_id}")
def update_holding(
    holding_id: int, body: HoldingUpdate, db: Session = Depends(get_db), portfolio: Portfolio = Depends(get_portfolio)
):
    h = _owned_holding(db, portfolio, holding_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(h, field, value)
    db.commit()
    return {"id": h.id, "symbol": h.symbol}


@router.delete("/holdings/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holding(holding_id: int, db: Session = Depends(get_db), portfolio: Portfolio = Depends(get_portfolio)):
    db.delete(_owned_holding(db, portfolio, holding_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
