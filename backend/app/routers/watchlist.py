"""
自訂追蹤清單（⭐ Watchlist）API。

GET    /api/watchlist            取得收藏清單（含報價、訊號、情緒）
POST   /api/watchlist            加入收藏 {"symbol": "NVDA"}
DELETE /api/watchlist/{symbol}   取消收藏
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import User, WatchlistItem
from ..schemas import StockCardOut, WatchlistIn
from ..services.analysis import analyze_symbols, quote_out, sentiment_out, signal_out
from ..services.symbols import InvalidSymbolError, normalize_symbol, symbol_info

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("", response_model=list[StockCardOut])
def read_watchlist(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = list(db.scalars(select(WatchlistItem).where(WatchlistItem.user_id == user.id).order_by(WatchlistItem.id)))
    analyses = analyze_symbols(db, [i.symbol for i in items])
    out = []
    for i in items:
        a, info = analyses[i.symbol], symbol_info(i.symbol)
        out.append(
            StockCardOut(
                symbol=i.symbol, name=a.name, market=info.market, currency=info.currency,
                quote=quote_out(a.quote), signal=signal_out(a.signal), sentiment=sentiment_out(a.digest),
                starred=True,
            )
        )
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
def add_to_watchlist(body: WatchlistIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    exists = db.scalar(select(WatchlistItem).where(WatchlistItem.user_id == user.id, WatchlistItem.symbol == body.symbol))
    if not exists:  # 重複加入視為成功（冪等 idempotent），前端不用特別處理
        db.add(WatchlistItem(user_id=user.id, symbol=body.symbol))
        db.commit()
    return {"symbol": body.symbol, "starred": True}


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_watchlist(symbol: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        sym = normalize_symbol(symbol)
    except InvalidSymbolError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    item = db.scalar(select(WatchlistItem).where(WatchlistItem.user_id == user.id, WatchlistItem.symbol == sym))
    if item:
        db.delete(item)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
