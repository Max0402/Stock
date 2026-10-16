# 系統架構與資料流（System Architecture）

## 1. 整體架構

```mermaid
flowchart LR
    subgraph Browser["🖥️ 瀏覽器"]
        UI["Next.js Dashboard<br/>React + Tailwind + Lightweight Charts"]
    end

    subgraph Next["Next.js Server :3000"]
        RW["rewrites<br/>/api/* → FastAPI"]
    end

    subgraph API["FastAPI :8000"]
        R["Routers<br/>portfolio / watchlist / stocks / jobs"]
        S["Services<br/>indicators · signals · sentiment · portfolio"]
        SCH["APScheduler<br/>每小時整點"]
        C["TTL Cache<br/>報價 60s · K線 15m · 匯率 1h"]
    end

    DB[("PostgreSQL / Supabase<br/>（本機：SQLite）")]
    YF["Yahoo Finance<br/>(yfinance)"]
    GN["新聞來源<br/>Yahoo Finance · Google News<br/>證交所重大訊息 · Finnhub"]
    AI["Claude API<br/>（選用）"]

    UI -- "fetch /api/... (SWR 輪詢)" --> RW --> R
    R --> S
    S --> C --> YF
    R <--> DB
    SCH -- "run_hourly_job()" --> S
    SCH --> GN
    SCH --> AI
    SCH --> DB
```

### 為什麼這樣分層？

| 層 | 負責 | 不負責 |
| --- | --- | --- |
| **前端（Next.js）** | 畫面、互動、定時輪詢（SWR） | 任何計算邏輯、API Key |
| **Next.js rewrites** | 把 `/api/*` 轉給後端 | — |
| **FastAPI Routers** | 驗證輸入、權限檢查、組合回應 | 計算細節 |
| **Services** | 純計算（指標、訊號、損益、情緒） | 知道 HTTP / 資料庫 |
| **Scheduler** | 每小時批次處理新聞與快照 | 回應使用者請求 |

> 💡 **把演算法放在 Python 後端**：pandas 計算方便、可以寫單元測試（`backend/tests/`），前端只負責「畫出來」。
> 前端換成 App、LINE Bot 也能重用同一套 API。

---

## 2. 兩條資料流

### A. 使用者開啟儀表板（即時，同步）

```mermaid
sequenceDiagram
    participant B as 瀏覽器
    participant N as Next.js
    participant F as FastAPI
    participant C as Cache
    participant Y as yfinance
    participant D as DB

    B->>N: GET /api/portfolio（每 60 秒）
    N->>F: 轉發
    F->>D: 讀取 holdings、watchlist、最新 news_digest
    par 每檔股票平行處理（ThreadPool）
        F->>C: 報價？
        C-->>Y: 快取過期才真的去抓
        F->>C: 日 K 歷史？
    end
    F->>F: 計算 RSI / 布林 / ATR → 買賣訊號<br/>計算市值 / 損益 / 報酬率（匯率換算）
    F-->>B: JSON（summary + holdings[]）
```

- **損益不存資料庫**：價格一直在變，所以每次查詢即時計算才正確（資料庫只存「股數、成本」這種事實）。
- **快取**：10 個人同時看台積電，Yahoo 只會被打 1 次。

### B. 每小時排程（背景，非同步）

```mermaid
sequenceDiagram
    participant S as APScheduler
    participant G as 新聞來源（4 個）
    participant A as Claude API
    participant D as DB

    S->>D: 要追蹤哪些股票？（持股 ∪ Watchlist ∪ 藍籌股）
    loop 每檔股票
        S->>G: 平行抓 Yahoo / Google News / 證交所 / Finnhub（近 48 小時）
        S->>S: 只留可信媒體白名單 → 同一則新聞多家轉載只留一筆
        S->>D: URL SHA-256 + 標題指紋去重複後存 news_articles（含每則情緒分數）
        S->>S: 挑出 Big News（重要性前 6 則）+ 時間加權情緒
        alt 新聞組合跟上次一樣
            S->>S: 跳過（不重複花 AI 費用）
        else 有新新聞
            S->>A: 產生 2 句摘要（有 API Key 才呼叫）
            A-->>S: JSON {sentiment, score, summary, impact}
            S->>D: 存 news_digests
        end
        S->>D: 存 signal_snapshots（之後可回測）
    end
    S->>D: 存 portfolio_snapshots（資產走勢）
```

排程的三種跑法（擇一）：

| 方式 | 適合 | 設定 |
| --- | --- | --- |
| 內建 APScheduler | 本機、單一伺服器 | `ENABLE_SCHEDULER=true`（預設） |
| 系統 crontab | VPS | `0 * * * * cd backend && .venv/bin/python -m app.jobs.hourly_news` |
| 外部 Cron 呼叫 API | Vercel / Render / 多 worker 部署 | `ENABLE_SCHEDULER=false`，排程服務呼叫 `POST /api/jobs/refresh-news`，Header 帶 `X-Cron-Secret` |

> ⚠️ 用 `uvicorn --workers 4` 時，每個 worker 都會各跑一份 APScheduler → 新聞會被重複抓 4 次。多 worker 請改用外部 Cron。

---

## 3. API 一覽

| Method | Path | 說明 |
| --- | --- | --- |
| GET | `/api/portfolio` | 投資組合總覽 + 每檔持股（報價、損益、訊號、情緒） |
| POST | `/api/holdings` | 新增持股 `{symbol, shares, buy_price, avg_cost?, note?}` |
| PATCH | `/api/holdings/{id}` | 修改持股 |
| DELETE | `/api/holdings/{id}` | 刪除持股 |
| GET | `/api/watchlist` | ⭐ 追蹤清單 |
| POST | `/api/watchlist` | 加入追蹤 `{symbol}`（重複加入也回成功＝冪等） |
| DELETE | `/api/watchlist/{symbol}` | 取消追蹤 |
| GET | `/api/stocks/{symbol}/chart?interval=1d\|1wk` | K 線 + MA/布林/RSI + 買賣標記 + 目前訊號 |
| GET | `/api/stocks/{symbol}/news` | AI 摘要 + 新聞列表（沒資料時現場抓一次） |
| GET | `/api/recommendations?market=ALL\|US\|TW` | 藍籌股推薦 + AI 評價 |
| POST | `/api/jobs/refresh-news` | 手動觸發排程（需 `X-Cron-Secret`） |
| GET | `/api/health` | 健康檢查 |

啟動後端後打開 <http://localhost:8000/docs> 可以直接在網頁上試打每一支 API（FastAPI 自動產生）。

---

## 4. 資料庫 Schema

完整 SQL：[`database/schema.sql`](../database/schema.sql)（已在 PostgreSQL 16 實測可執行）。

```mermaid
erDiagram
    users ||--o{ portfolios : has
    portfolios ||--o{ holdings : contains
    users ||--o{ watchlist : stars
    portfolios ||--o{ portfolio_snapshots : "hourly value"

    users {
        bigint id PK
        varchar email UK
        varchar display_name
        char base_currency "TWD / USD / AUD"
    }
    portfolios {
        bigint id PK
        bigint user_id FK
        varchar name
    }
    holdings {
        bigint id PK
        bigint portfolio_id FK
        varchar symbol "AAPL / 2330.TW"
        char market "US / TW"
        char currency
        numeric shares "CHECK > 0"
        numeric buy_price
        numeric avg_cost
    }
    watchlist {
        bigint id PK
        bigint user_id FK
        varchar symbol
    }
    news_articles {
        bigint id PK
        varchar symbol
        char url_hash "UNIQUE(symbol,url_hash)"
        text title
        float sentiment_score
        float importance
    }
    news_digests {
        bigint id PK
        varchar symbol
        varchar sentiment_label
        text summary "第 1 句"
        text impact "第 2 句"
        varchar method "llm / rule"
    }
    signal_snapshots {
        bigint id PK
        varchar symbol
        numeric buy_zone_low
        numeric take_profit
        numeric stop_loss
        varchar action
    }
```

設計重點：

- **金額用 `NUMERIC`**，不用 `FLOAT`：浮點數會有 `0.1 + 0.2 = 0.30000000000000004` 的誤差。
- **`UNIQUE(portfolio_id, symbol)`**：同一個投資組合不會出現兩筆 AAPL（要加碼就編輯平均成本）。
- **`CHECK (shares > 0)`**：就算後端程式有 bug，資料庫也會擋下負數股數（縱深防禦）。
- **新聞以股票為單位共用**：100 個人都持有台積電，新聞只需要抓一份。
- **時間一律 `TIMESTAMPTZ`（UTC）**：台灣、澳洲、美國使用者看到的都是自己的當地時間。

---

## 5. 安全性設計（Security Notes）

| 風險 | 本專案的做法 | 檔案 |
| --- | --- | --- |
| 惡意輸入 / Injection | 股票代碼白名單 Regex；ORM 參數化查詢（不拼 SQL 字串） | `services/symbols.py` |
| IDOR（改網址 id 動到別人資料） | 查詢持股一定同時比對 `portfolio_id` | `routers/portfolio.py` |
| 排程 API 被濫用 | 未設定密鑰 → 404；比對用 `secrets.compare_digest` 防計時攻擊 | `routers/jobs.py` |
| 新聞雜訊 / 內容農場 | 只保留可信媒體白名單；網域比對加點號，避免 `evilreuters.com` 冒充 `reuters.com` | `services/news_sources.py` |
| API Key 外洩到 log | Finnhub Key 用 `X-Finnhub-Token` Header 傳送，不放在網址上 | `services/news.py` |
| XSS（新聞連結 `javascript:`） | 後端只收 http(s) 連結，前端再用 `safeExternalUrl` 檢查一次 | `services/news.py`、`lib/format.ts` |
| Reverse tabnabbing | 外部連結加 `rel="noopener noreferrer"` | `NewsPanel.tsx` |
| Prompt Injection（新聞標題要 AI 改答案） | 新聞放在 `<news>` 區塊並聲明是資料；Structured Output 固定格式；回傳值再驗證 / 夾住範圍 | `services/llm.py` |
| 機密外洩 | API Key 只放後端 `.env`（已加入 `.gitignore`），前端完全拿不到 | `config.py` |
| CORS | 只允許設定的前端網域，不用 `*` | `main.py` |

> 🔐 **目前是單人 Demo 模式**（`deps.py` 固定回傳 demo user）。要多人使用，請接上 Supabase Auth / NextAuth 並在 `get_current_user` 驗證 JWT——**永遠不要相信前端直接傳來的 user_id**。
