"""
新聞情緒分析（規則式 NLP，免費、離線、可解釋）。

流程
----
1. 單則新聞：標題比對「金融情緒詞典」（中英文都有），命中正面詞加分、負面詞扣分。
   - 否定詞處理：「not beat」「未達」→ 分數反轉。
   - 分數用 tanh 壓縮到 −1 ~ +1（避免一則新聞命中很多詞就分數爆表）。
2. 單則新聞重要性（importance）：情緒強度 + 是否為「重大事件」（財報、併購、法說會…）。
   → 用來挑出「Big News」。
3. 整檔股票的情緒：近期新聞的「時間加權平均」，半衰期 24 小時（越新的新聞權重越高）。

為什麼不直接全部丟給 AI？
- 每小時 × 每檔股票 × 每則新聞都呼叫 LLM 很貴，而且慢。
- 規則式結果可解釋、可測試，也能當 AI 失敗時的備援（fallback）。
- 有設定 ANTHROPIC_API_KEY 時，llm.py 會在這個基礎上產生更自然的摘要。
"""

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

SentimentLabel = Literal["Bullish", "Bearish", "Neutral"]
LABEL_THRESHOLD = 0.15
HALF_LIFE_HOURS = 24.0

# ── 英文詞典（權重：越大代表越強烈）──────────────────────────────
EN_POSITIVE: dict[str, float] = {
    "beat": 1.0, "beats estimates": 1.4, "tops estimates": 1.4, "record": 0.8,
    "surge": 1.0, "soar": 1.2, "jump": 0.8, "rally": 0.8, "climb": 0.5, "gain": 0.4,
    "upgrade": 1.2, "outperform": 1.0, "overweight": 0.8, "buy rating": 0.8,
    "raises guidance": 1.5, "raised guidance": 1.5, "raises forecast": 1.3, "boosts outlook": 1.3,
    "strong demand": 1.0, "strong growth": 1.0, "growth": 0.4, "profit": 0.4, "expands": 0.5,
    "buyback": 0.8, "dividend hike": 0.9, "partnership": 0.6, "approval": 0.8, "approved": 0.8,
    "breakthrough": 0.9, "all-time high": 1.0, "wins contract": 1.0, "bullish": 1.0,
}
EN_NEGATIVE: dict[str, float] = {
    "miss": -1.0, "misses estimates": -1.4, "plunge": -1.2, "tumble": -1.0, "slump": -1.0,
    "fall": -0.6, "drop": -0.6, "dropped": -0.6, "sink": -0.8, "slide": -0.6, "decline": -0.6,
    "downgrade": -1.2, "underperform": -1.0, "underweight": -0.8, "sell rating": -0.8,
    "cuts guidance": -1.5, "lowers guidance": -1.5, "cut forecast": -1.3, "warns": -0.9,
    "lawsuit": -0.8, "probe": -0.8, "investigation": -0.8, "antitrust": -0.7, "fine": -0.5,
    "recall": -1.0, "layoffs": -0.6, "tariff": -0.6, "ban": -0.8, "sanction": -0.8,
    "sell-off": -1.0, "selloff": -1.0, "weak demand": -1.0, "loss": -0.6, "fraud": -1.5,
    "bankruptcy": -2.0, "delay": -0.5, "shortage": -0.5, "bearish": -1.0,
}
# ── 中文詞典（台股新聞常見用語）──────────────────────────────────
ZH_POSITIVE: dict[str, float] = {
    "創新高": 1.0, "創高": 0.8, "大漲": 1.0, "漲停": 1.5, "上漲": 0.5, "勁揚": 0.8, "飆": 0.8,
    "上修": 1.2, "調升": 1.0, "優於預期": 1.3, "利多": 1.2, "看好": 0.8, "買超": 0.8,
    "成長": 0.6, "獲利": 0.5, "強勁": 0.8, "突破": 0.6, "擴產": 0.6, "大單": 0.9, "訂單": 0.4,
    "加碼": 0.7, "回購": 0.8, "配息": 0.4, "旺季": 0.6, "目標價調高": 1.2,
}
ZH_NEGATIVE: dict[str, float] = {
    "大跌": -1.0, "跌停": -1.5, "重挫": -1.2, "下跌": -0.5, "走弱": -0.7, "崩": -1.0,
    "下修": -1.2, "調降": -1.0, "不如預期": -1.3, "低於預期": -1.3, "利空": -1.2, "看壞": -0.8,
    "賣超": -0.8, "衰退": -1.0, "虧損": -1.0, "裁員": -0.6, "制裁": -0.8, "關稅": -0.6,
    "減產": -0.6, "砍單": -1.2, "淡季": -0.5, "違約": -1.2, "罰款": -0.6, "目標價調降": -1.2,
}

EN_NEGATIONS = {"not", "no", "never", "without", "fails", "failed", "didn't", "doesn't", "won't"}
ZH_NEGATIONS = ("不", "未", "沒", "無")

# 「重大事件」關鍵字：命中就提高重要性，優先列為 Big News
BIG_EVENT_KEYWORDS = (
    "earnings", "guidance", "revenue", "acquisition", "acquire", "merger", "fda", "sec",
    "lawsuit", "ceo", "split", "dividend", "buyback", "tariff", "antitrust", "forecast",
    "財報", "營收", "法說會", "併購", "收購", "股利", "配息", "減資", "增資", "董事會", "關稅", "財測",
)


def _compile_en(terms: dict[str, float]) -> list[tuple[re.Pattern, float]]:
    # \b 是「單字邊界」：避免 "loss" 誤中 "glossy"；後面允許常見字尾（beats / surged / jumping）
    return [
        (re.compile(rf"\b{re.escape(t)}(?:s|es|ed|d|ing)?\b", re.IGNORECASE), w) for t, w in terms.items()
    ]


_EN_PATTERNS = _compile_en(EN_POSITIVE) + _compile_en(EN_NEGATIVE)


@dataclass
class ArticleSentiment:
    score: float           # −1 ~ +1
    label: SentimentLabel
    importance: float      # 0 ~ 2，越大越重要
    matched: list[str]     # 命中的詞（除錯 / 解釋用）


def label_for(score: float) -> SentimentLabel:
    if score > LABEL_THRESHOLD:
        return "Bullish"
    if score < -LABEL_THRESHOLD:
        return "Bearish"
    return "Neutral"


def _is_negated_en(text: str, start: int) -> bool:
    """看命中位置前面 3 個單字有沒有否定詞。"""
    before = re.findall(r"[a-z']+", text[:start].lower())[-3:]
    return any(w in EN_NEGATIONS for w in before)


def score_text(text: str) -> ArticleSentiment:
    raw = 0.0
    matched: list[str] = []

    # 英文：用 regex 比對；已被較長片語命中的位置不重複計分（"beats estimates" 不會再算一次 "beat"）
    used: list[tuple[int, int]] = []
    for pattern, weight in sorted(_EN_PATTERNS, key=lambda p: -len(p[0].pattern)):
        for m in pattern.finditer(text):
            if any(s < m.end() and m.start() < e for s, e in used):
                continue
            used.append((m.start(), m.end()))
            w = -weight if _is_negated_en(text, m.start()) else weight
            raw += w
            matched.append(m.group(0))

    # 中文：沒有空白分詞，直接子字串比對；前 2 個字內有「不/未/沒/無」就反轉
    zh_terms = {**ZH_POSITIVE, **ZH_NEGATIVE}
    masked = text
    for term in sorted(zh_terms, key=len, reverse=True):
        idx = masked.find(term)
        while idx != -1:
            weight = zh_terms[term]
            # 「不如預期」本身就含「不」，這種詞不再做否定判斷
            negated = not term.startswith(ZH_NEGATIONS) and any(
                n in masked[max(0, idx - 2) : idx] for n in ZH_NEGATIONS
            )
            raw += -weight if negated else weight
            matched.append(term)
            # 把已命中的字遮掉，避免「目標價調高」再被「調高」重複計分
            masked = masked[:idx] + "□" * len(term) + masked[idx + len(term) :]
            idx = masked.find(term, idx + len(term))

    score = math.tanh(raw / 2)  # 壓縮到 −1 ~ +1
    lower = text.lower()
    big_event = any(k in lower for k in BIG_EVENT_KEYWORDS)
    importance = abs(score) + (1.0 if big_event else 0.0)
    return ArticleSentiment(score=round(score, 4), label=label_for(score), importance=round(importance, 4), matched=matched)


def aggregate_sentiment(
    items: list[tuple[float, datetime]], now: datetime | None = None
) -> tuple[float, SentimentLabel]:
    """
    items：[(單則分數, 發布時間), ...]
    回傳：時間加權平均分數與標籤。
    權重 = 0.5 ^ (經過小時 / 24)：剛發布的新聞權重 1，一天前 0.5，兩天前 0.25…
    """
    if not items:
        return 0.0, "Neutral"
    now = now or datetime.now(timezone.utc)
    total_w = total = 0.0
    for score, published in items:
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        age_h = max((now - published).total_seconds() / 3600, 0)
        w = 0.5 ** (age_h / HALF_LIFE_HOURS)
        total += score * w
        total_w += w
    avg = total / total_w if total_w else 0.0
    return round(avg, 4), label_for(avg)


_IMPACT_TEXT: dict[SentimentLabel, str] = {
    "Bullish": "消息面偏多，短線可能支撐股價；但若股價已接近布林上軌，追高前請先確認風報比。",
    "Bearish": "消息面偏空，短線可能對股價形成壓力，持有者建議留意停損價位、等待情緒回穩。",
    "Neutral": "消息面影響有限，短線走勢仍以技術面與大盤方向為主。",
}
_LABEL_ZH: dict[SentimentLabel, str] = {"Bullish": "偏多", "Bearish": "偏空", "Neutral": "中性"}


def rule_based_digest(
    display_name: str, headlines: list[str], score: float, label: SentimentLabel
) -> tuple[str, str]:
    """
    沒有 AI 時的備援摘要：固定模板，產生 2 句話（摘要 + 影響評估）。
    headlines 請依重要性排序，第一則會被當成「焦點新聞」。
    """
    if not headlines:
        return (f"{display_name} 近 24 小時沒有重大新聞。", _IMPACT_TEXT["Neutral"])
    top = headlines[0] if len(headlines[0]) <= 60 else headlines[0][:57] + "…"
    summary = (
        f"{display_name} 近期共 {len(headlines)} 則重點新聞，整體情緒{_LABEL_ZH[label]}"
        f"（分數 {score:+.2f}），焦點為「{top}」。"
    )
    return summary, _IMPACT_TEXT[label]
