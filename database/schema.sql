-- ════════════════════════════════════════════════════════════════════
-- 個人化股票追蹤 App —— PostgreSQL / Supabase Schema
-- 執行方式：psql "$DATABASE_URL" -f database/schema.sql
-- （本機用 SQLite 開發時，後端啟動會依 ORM Model 自動建表，不需要執行這個檔案）
-- ════════════════════════════════════════════════════════════════════

-- ── 1. 使用者 ───────────────────────────────────────────────────────
-- 若使用 Supabase Auth，可把 id 改成 UUID 並 REFERENCES auth.users(id)
CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    display_name    VARCHAR(100) NOT NULL,
    base_currency   CHAR(3)      NOT NULL DEFAULT 'TWD',   -- 投資組合加總用的幣別
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ── 2. 投資組合（一個使用者可有多個，例如「長期」「短線」）─────────
CREATE TABLE IF NOT EXISTS portfolios (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        VARCHAR(100) NOT NULL DEFAULT '我的投資組合',
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (user_id, name)
);

-- ── 3. 持股 ─────────────────────────────────────────────────────────
-- 總市值 / 損益 / 報酬率「不存」在資料庫：價格每分鐘都在變，查詢時即時計算才正確。
CREATE TABLE IF NOT EXISTS holdings (
    id            BIGSERIAL PRIMARY KEY,
    portfolio_id  BIGINT         NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    symbol        VARCHAR(20)    NOT NULL,                 -- AAPL、2330.TW、6488.TWO
    market        CHAR(2)        NOT NULL CHECK (market IN ('US', 'TW')),
    currency      CHAR(3)        NOT NULL,                 -- USD / TWD
    shares        NUMERIC(20, 6) NOT NULL CHECK (shares > 0),
    buy_price     NUMERIC(20, 6) NOT NULL CHECK (buy_price > 0),   -- 首次買入單價
    avg_cost      NUMERIC(20, 6) NOT NULL CHECK (avg_cost > 0),    -- 目前平均成本（算損益用）
    note          VARCHAR(500),
    created_at    TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ    NOT NULL DEFAULT now(),
    UNIQUE (portfolio_id, symbol)
);

-- ── 4. 自訂追蹤（⭐ Watchlist）─────────────────────────────────────
CREATE TABLE IF NOT EXISTS watchlist (
    id        BIGSERIAL PRIMARY KEY,
    user_id   BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol    VARCHAR(20) NOT NULL,
    added_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, symbol)
);

-- ── 5. 新聞（以股票為單位，所有使用者共用；url_hash 去重複）────────
CREATE TABLE IF NOT EXISTS news_articles (
    id               BIGSERIAL PRIMARY KEY,
    symbol           VARCHAR(20) NOT NULL,
    url_hash         CHAR(64)    NOT NULL,                 -- SHA-256(url)
    title            TEXT        NOT NULL,
    url              TEXT        NOT NULL,
    source           VARCHAR(200),
    published_at     TIMESTAMPTZ NOT NULL,
    sentiment_score  DOUBLE PRECISION NOT NULL,            -- −1 ~ +1
    sentiment_label  VARCHAR(10) NOT NULL CHECK (sentiment_label IN ('Bullish', 'Bearish', 'Neutral')),
    importance       DOUBLE PRECISION NOT NULL DEFAULT 0,  -- 越高越可能是 Big News
    fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (symbol, url_hash)
);
CREATE INDEX IF NOT EXISTS ix_news_articles_symbol_published ON news_articles (symbol, published_at DESC);

-- ── 6. 每小時 AI 新聞摘要（2 句：摘要 + 市場影響）─────────────────
CREATE TABLE IF NOT EXISTS news_digests (
    id               BIGSERIAL PRIMARY KEY,
    symbol           VARCHAR(20) NOT NULL,
    generated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    sentiment_label  VARCHAR(10) NOT NULL CHECK (sentiment_label IN ('Bullish', 'Bearish', 'Neutral')),
    sentiment_score  DOUBLE PRECISION NOT NULL,
    summary          TEXT        NOT NULL,
    impact           TEXT        NOT NULL,
    article_count    INTEGER     NOT NULL,
    method           VARCHAR(10) NOT NULL CHECK (method IN ('llm', 'rule')),
    input_hash       CHAR(64)    NOT NULL                  -- 新聞組合沒變就不重算（省 AI 費用）
);
CREATE INDEX IF NOT EXISTS ix_news_digests_symbol_generated ON news_digests (symbol, generated_at DESC);

-- ── 7. 買賣訊號歷史（可用來回測演算法準確度）──────────────────────
CREATE TABLE IF NOT EXISTS signal_snapshots (
    id             BIGSERIAL PRIMARY KEY,
    symbol         VARCHAR(20)    NOT NULL,
    computed_at    TIMESTAMPTZ    NOT NULL DEFAULT now(),
    close          NUMERIC(20, 6) NOT NULL,
    rsi            DOUBLE PRECISION NOT NULL,
    percent_b      DOUBLE PRECISION NOT NULL,
    buy_zone_low   NUMERIC(20, 6) NOT NULL,
    buy_zone_high  NUMERIC(20, 6) NOT NULL,
    take_profit    NUMERIC(20, 6) NOT NULL,
    stop_loss      NUMERIC(20, 6) NOT NULL,
    trailing_stop  NUMERIC(20, 6) NOT NULL,
    action         VARCHAR(12)    NOT NULL CHECK (action IN ('STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL')),
    score          DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_signal_snapshots_symbol_computed ON signal_snapshots (symbol, computed_at DESC);

-- ── 8. 投資組合市值歷史（每小時一筆，畫資產走勢圖用）──────────────
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    portfolio_id    BIGINT         NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    taken_at        TIMESTAMPTZ    NOT NULL DEFAULT now(),
    currency        CHAR(3)        NOT NULL,
    market_value    NUMERIC(20, 6) NOT NULL,
    cost_basis      NUMERIC(20, 6) NOT NULL,
    unrealized_pnl  NUMERIC(20, 6) NOT NULL,
    day_pnl         NUMERIC(20, 6) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_portfolio_snapshots_portfolio_taken ON portfolio_snapshots (portfolio_id, taken_at DESC);

-- ════════════════════════════════════════════════════════════════════
-- （選用）Supabase Row Level Security：讓使用者只能讀寫自己的資料
-- 前提：users.id 改為 UUID 並對應 auth.uid()
-- ════════════════════════════════════════════════════════════════════
-- ALTER TABLE holdings  ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "own holdings" ON holdings
--   USING (portfolio_id IN (SELECT id FROM portfolios WHERE user_id = auth.uid()));
-- ALTER TABLE watchlist ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "own watchlist" ON watchlist USING (user_id = auth.uid());
