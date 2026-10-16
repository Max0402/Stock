"""
FastAPI Dependencies：取得「目前使用者」與「他的投資組合」。

「目前使用者是誰」來自 security.py 驗證過的帳號（request.state.username），
不是前端傳來的參數 —— 千萬不要相信前端傳來的 user_id（任何人都可以改，這就是 IDOR 漏洞）。

帳號對應方式
------------
- 網站擁有者（APP_USERNAME）或沒有啟用登入時 → 原本的那個使用者（保留你已經輸入的持股）
- 朋友（APP_USERS 裡的帳號）→ 第一次登入時自動建立專屬的使用者與投資組合

想開放陌生人自行註冊：需要真正的帳號系統（例如 Supabase Auth + JWT，或自己做密碼雜湊 + Session），
只要把這裡改成「從驗證過的 token 取出使用者」即可，其他 API 都不用改。
"""

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Portfolio, User

OWNER_EMAIL = "demo@example.com"  # 沿用最早的單人模式帳號，升級後資料不會不見


def _account_email(username: str) -> str:
    return f"{username.lower()}@accounts.local"  # 只是內部識別用，不會寄信


def _get_or_create(db: Session, email: str, display_name: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        return user
    user = User(email=email, display_name=display_name, base_currency=get_settings().base_currency)
    user.portfolios.append(Portfolio(name="我的投資組合"))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # 朋友第一次打開網頁時，前端會同時送出好幾個請求 → 可能同時嘗試建立同一個帳號。
        # 資料庫的 UNIQUE(email) 會擋下第二個，這時改用第一個建立好的就好。
        db.rollback()
        user = db.scalar(select(User).where(User.email == email))
    return user


def ensure_demo_user(db: Session) -> User:
    """網站擁有者 / 單人模式的帳號。"""
    return _get_or_create(db, OWNER_EMAIL, "Demo")


def user_for_username(db: Session, username: str | None) -> User:
    if username is None or username == get_settings().app_username:
        return ensure_demo_user(db)
    return _get_or_create(db, _account_email(username), username)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    return user_for_username(db, getattr(request.state, "username", None))


def get_portfolio(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Portfolio:
    portfolio = db.scalar(select(Portfolio).where(Portfolio.user_id == user.id).order_by(Portfolio.id))
    if portfolio is None:
        portfolio = Portfolio(user_id=user.id, name="我的投資組合")
        db.add(portfolio)
        db.commit()
    return portfolio
