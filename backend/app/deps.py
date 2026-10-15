"""
FastAPI Dependencies：取得「目前使用者」與「預設投資組合」。

⚠️ 目前為單人模式（Demo User），方便本機學習與開發。
正式上線多人使用時，請把 get_current_user 換成真正的驗證，例如：
  1. 前端用 Supabase Auth / NextAuth 登入，拿到 JWT
  2. 前端每個請求帶 Authorization: Bearer <token>
  3. 這裡驗證 JWT 簽章與過期時間，從 token 的 sub 取出 user id
  千萬不要直接相信前端傳來的 user_id（任何人都可以改，這就是 IDOR 漏洞）。
"""

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Portfolio, User

DEMO_EMAIL = "demo@example.com"


def ensure_demo_user(db: Session) -> User:
    user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if user is None:
        user = User(email=DEMO_EMAIL, display_name="Demo", base_currency=get_settings().base_currency)
        user.portfolios.append(Portfolio(name="我的投資組合"))
        db.add(user)
        db.commit()
    return user


def get_current_user(db: Session = Depends(get_db)) -> User:
    return ensure_demo_user(db)


def get_portfolio(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Portfolio:
    portfolio = db.scalar(select(Portfolio).where(Portfolio.user_id == user.id).order_by(Portfolio.id))
    if portfolio is None:
        portfolio = Portfolio(user_id=user.id, name="我的投資組合")
        db.add(portfolio)
        db.commit()
    return portfolio
