from datetime import datetime, timedelta, timezone

from app.services.sentiment import aggregate_sentiment, label_for, rule_based_digest, score_text


def test_english_positive_and_negative():
    assert score_text("Nvidia beats estimates, raises guidance").label == "Bullish"
    assert score_text("Tesla shares plunge after analyst downgrade").label == "Bearish"
    assert score_text("Apple to hold annual event in September").label == "Neutral"


def test_english_negation_flips():
    assert score_text("Company did not beat expectations").score < 0


def test_phrase_not_double_counted():
    # "beats estimates" 是片語，不應再額外算一次 "beat"
    s = score_text("XYZ beats estimates")
    assert s.matched == ["beats estimates"]


def test_chinese_terms_and_negation():
    assert score_text("台積電營收創新高，法人看好").label == "Bullish"
    assert score_text("聯發科財測下修，外資賣超").label == "Bearish"
    assert score_text("市場不看好鴻海新產品").score < 0     # 「不」+「看好」→ 反轉
    assert score_text("廣達營收不如預期").score < 0         # 本身含「不」的負面詞不會被反轉成正面


def test_big_event_increases_importance():
    plain = score_text("Apple shares rally")
    event = score_text("Apple shares rally after earnings")
    assert event.importance > plain.importance


def test_aggregate_recency_weighting():
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    items = [(1.0, now), (-1.0, now - timedelta(hours=48))]  # 新的利多 vs 兩天前的利空
    score, label = aggregate_sentiment(items, now=now)
    assert score > 0.5 and label == "Bullish"
    assert aggregate_sentiment([], now=now) == (0.0, "Neutral")


def test_labels_and_digest():
    assert label_for(0.2) == "Bullish" and label_for(-0.2) == "Bearish" and label_for(0.1) == "Neutral"
    summary, impact = rule_based_digest("台積電", ["台積電法說會優於預期"], 0.5, "Bullish")
    assert "台積電" in summary and "偏多" in summary and impact
