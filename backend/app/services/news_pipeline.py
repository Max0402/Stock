"""
單檔股票的新聞處理流程（排程與 API 都會用到）：

    抓新聞 → 去重複存 DB → 每則算情緒 → 挑出 Big News → 整體情緒加權
          → 產生 2 句摘要（Claude 或規則式）→ 存成 NewsDigest
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import NewsArticle, NewsDigest
from .llm import summarize_news
from .news import fetch_news, title_key, url_hash
from .news_sources import TIER_BONUS, tier_of
from .sentiment import aggregate_sentiment, rule_based_digest, score_text

log = logging.getLogger(__name__)

DIGEST_WINDOW_HOURS = 48   # 摘要只看最近 48 小時
BIG_NEWS_COUNT = 6         # 挑最重要的 6 則送去摘要


@dataclass
class RefreshResult:
    new_articles: int = 0
    digest_created: bool = False
    llm_called: bool = False


def latest_digest(db: Session, symbol: str) -> NewsDigest | None:
    return db.scalar(select(NewsDigest).where(NewsDigest.symbol == symbol).order_by(NewsDigest.id.desc()).limit(1))


def refresh_symbol_news(db: Session, symbol: str, display_name: str) -> RefreshResult:
    result = RefreshResult()

    # 1) 抓新聞並去重複：
    #    (a) 同一個網址（SHA-256）已存過 → 跳過
    #    (b) 網址不同但標題相同（同一則新聞被不同網站轉載）→ 也跳過
    raw = fetch_news(symbol)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=DIGEST_WINDOW_HOURS)
    hashes = {url_hash(a.key): a for a in raw}
    existing = set(
        db.scalars(
            select(NewsArticle.url_hash).where(NewsArticle.symbol == symbol, NewsArticle.url_hash.in_(list(hashes)))
        )
    )
    seen_titles = {
        title_key(t)
        for t in db.scalars(
            select(NewsArticle.title).where(NewsArticle.symbol == symbol, NewsArticle.published_at >= cutoff)
        )
    }
    for h, a in hashes.items():
        if h in existing or title_key(a.title) in seen_titles:
            continue
        seen_titles.add(title_key(a.title))
        s = score_text(a.title)
        db.add(
            NewsArticle(
                symbol=symbol, url_hash=h, title=a.title, url=a.url, source=a.source,
                published_at=a.published_at, sentiment_score=s.score, sentiment_label=s.label,
                # 官方公告、主流媒體的新聞比較容易被選為 Big News
                importance=round(s.importance + TIER_BONUS.get(a.tier, 0.0), 4),
            )
        )
        result.new_articles += 1
    db.flush()

    # 2) 挑出近 48 小時「最重要」的新聞（= Big News）
    big_news = list(
        db.scalars(
            select(NewsArticle)
            .where(NewsArticle.symbol == symbol, NewsArticle.published_at >= cutoff)
            .order_by(NewsArticle.importance.desc(), NewsArticle.published_at.desc())
            .limit(BIG_NEWS_COUNT)
        )
    )
    score, label = aggregate_sentiment([(a.sentiment_score, a.published_at) for a in big_news])

    # 3) 新聞組合跟上次一樣 → 不重新產生摘要（省下 AI 費用）
    input_hash = hashlib.sha256("|".join(sorted(a.url_hash for a in big_news)).encode()).hexdigest()
    last = latest_digest(db, symbol)
    if last is not None and last.input_hash == input_hash:
        db.commit()
        return result

    # 4) 產生摘要：優先用 Claude，失敗或沒設定 API Key 就用規則式
    headlines = [
        {"title": a.title, "source": a.source, "tier": tier_of(a.source, a.url), "published_at": a.published_at.isoformat()}
        for a in big_news
    ]
    llm = summarize_news(display_name, headlines, score) if big_news else None
    result.llm_called = llm is not None
    if llm:
        summary, impact, final_label, final_score, method = llm.summary, llm.impact, llm.sentiment, llm.score, "llm"
    else:
        summary, impact = rule_based_digest(display_name, [a.title for a in big_news], score, label)
        final_label, final_score, method = label, score, "rule"

    db.add(
        NewsDigest(
            symbol=symbol, sentiment_label=final_label, sentiment_score=final_score, summary=summary,
            impact=impact, article_count=len(big_news), method=method, input_hash=input_hash,
        )
    )
    db.commit()
    result.digest_created = True
    return result
