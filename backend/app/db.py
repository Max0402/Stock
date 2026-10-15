"""
資料庫連線（SQLAlchemy 2.0）。

- engine：資料庫連線池
- SessionLocal：每個請求 / 每次排程各自拿一個 Session（交易單位）
- get_db：FastAPI 的 dependency，請求結束自動關閉 Session
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    """所有 ORM Model 的父類別。"""


def _make_engine(url: str):
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        # SQLite 預設只允許建立連線的執行緒使用；
        # 我們的排程在背景執行緒跑，所以要關掉這個檢查。
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """
    開發階段直接依照 ORM Model 建表（已存在的表不會被動到）。
    正式環境建議改用 Alembic 做 migration，或直接執行 database/schema.sql。
    """
    from . import models  # noqa: F401  ← 匯入才會把資料表註冊到 Base.metadata

    Base.metadata.create_all(engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
