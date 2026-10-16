# 📈 個人化股票追蹤與分析 Web App

美股 + 台股持股管理、K 線技術分析、演算法買賣價位、每小時 AI 新聞情緒摘要。

![Dashboard](docs/screenshot.png)

| 功能 | 說明 |
| --- | --- |
| 🧾 多市場持股管理 | 輸入代碼（`AAPL`、`2330` 自動補 `.TW`）、股數、買入價、平均成本 → 自動算總市值、未實現損益、今日損益、報酬率；美股以匯率換算成台幣加總 |
| 🕯️ K 線圖 | 日 K / 週 K 切換，MA5/20/60、布林通道、RSI 副圖可開關（TradingView Lightweight Charts） |
| 🎯 買賣訊號 | RSI + 布林通道 + 均線趨勢 + 新聞情緒 → 強力買進 / 買進 / 觀望 / 賣出；標出 **Buy Zone、停利 TP、停損 SL、移動停損** |
| 📰 每小時新聞分析 | 排程從 Yahoo Finance、Google News（只取可信媒體）、證交所重大訊息、Finnhub 抓新聞 → 中英文情緒分析（Bullish / Bearish / Neutral）→ 2 句 AI 摘要與市場影響評估 |
| ⭐ 追蹤清單 | 任何卡片點星星即可收藏 |
| 🔥 藍籌股推薦 | NVDA、TSLA、AAPL、2330、2454… 基本面簡介 + 目前 AI 評價，一鍵加入追蹤 |
| 🔴🟢 漲跌色切換 | 台灣「紅漲綠跌」/ 美國「綠漲紅跌」一鍵切換 |

---

## 📚 文件導覽（對應需求的 5 個項目）

| # | 需求 | 在哪裡 |
| --- | --- | --- |
| 1 | 系統架構與資料流 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| 2 | 資料庫 Schema | [`database/schema.sql`](database/schema.sql)（PostgreSQL / Supabase）· ORM：[`backend/app/models.py`](backend/app/models.py) |
| 3 | 買賣點與新聞演算法 | [`docs/ALGORITHM.md`](docs/ALGORITHM.md) · 程式：[`signals.py`](backend/app/services/signals.py)、[`sentiment.py`](backend/app/services/sentiment.py) |
| 4 | 前端 Dashboard 元件 | [`frontend/components/`](frontend/components/)（見下方結構） |
| 5 | 後端每小時 Cron Job | [`backend/app/jobs/hourly_news.py`](backend/app/jobs/hourly_news.py) · 排程設定：[`backend/app/main.py`](backend/app/main.py) |

---

## 🚀 快速開始

需要：**Python 3.10 以上**（已確認 Windows 上的 3.13 / 3.14 / 3.15 都能直接安裝，不需要 C++ 編譯器）、**Node.js 20.9+**

> Windows 的 PowerShell 如果出現「已停用指令碼執行」，先執行 `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`（只對目前這個視窗有效），再啟動虛擬環境。

### 1. 後端（FastAPI）

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows：.venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # 依需要修改

uvicorn app.main:app --reload --port 8000
```

- API 文件（可直接在網頁上測試）：<http://localhost:8000/docs>
- 啟動時會先跑一次新聞排程，之後每小時整點自動執行。
- **沒有網路 / Yahoo 被擋？** 把 `.env` 的 `DATA_PROVIDER` 改成 `demo`，會使用離線假資料，整個 App 一樣能完整操作。

### 2. 前端（Next.js）

```bash
cd frontend
npm install
npm run dev
```

打開 <http://localhost:3000>。前端的 `/api/*` 會由 Next.js 轉發到 `http://localhost:8000`（可用環境變數 `BACKEND_URL` 修改）。

### 3. 確認 Yahoo Finance 與新聞來源連得上

```bash
cd backend
python -m app.check_sources AAPL 2330.TW
```

會逐一列出：報價、日 K、每個新聞來源抓到幾則、其中幾則來自可信媒體。看到 ❌ 就代表那個來源連不上（把訊息貼給我就能幫你查）。

### 4.（選用）啟用 Claude AI 新聞摘要

在 `backend/.env` 填入 `ANTHROPIC_API_KEY=...`。沒填也可以用：系統會改用內建的規則式摘要（卡片上的圖示 🤖 = 規則式、✨ = AI）。
預設模型是 `claude-opus-5-5`，可用 `ANTHROPIC_MODEL` 修改。新聞沒有變化時不會重複呼叫，以節省費用。

### 5.（選用）改用 PostgreSQL / Supabase

```bash
# 例：用 Docker 開一個本機 PostgreSQL
docker run -d --name stock-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=stock -p 5432:5432 postgres:16

psql "postgresql://postgres:postgres@localhost:5432/stock" -f database/schema.sql
```

然後在 `backend/.env` 設定：

```
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/stock
```

Supabase：到 Project Settings → Database 複製連線字串，把開頭的 `postgresql://` 改成 `postgresql+psycopg://` 即可。

---

## 📰 新聞來源與可信媒體白名單

| 來源 | 適用 | 需要 Key？ | 說明 |
| --- | --- | --- | --- |
| **Yahoo Finance** | 美股、台股 | 不用 | yfinance 個股新聞，原始發布者（Reuters、Bloomberg…）會被保留下來 |
| **Google News RSS** | 美股、台股 | 不用 | 搜尋時用 `site:` 只找可信媒體；台股用繁中搜尋 |
| **證交所重大訊息** | 上市股（`.TW`） | 不用 | [TWSE OpenAPI](https://openapi.twse.com.tw/)「上市公司每日重大訊息」，官方第一手資料 |
| **Finnhub** | 美股 | 免費 Key | 在 `.env` 設定 `FINNHUB_API_KEY` 才會啟用 |

抓回來的新聞只保留白名單裡的發布者（`NEWS_TRUSTED_ONLY=true`），分三級，並顯示在新聞面板：

- **官方公告**：公開資訊觀測站（證交所）
- **主流媒體**：Reuters、Bloomberg、CNBC、WSJ、MarketWatch、Barron's、Financial Times、AP、Yahoo Finance、中央社、經濟日報、工商時報、鉅亨網、MoneyDJ、今周刊、天下雜誌、DIGITIMES、自由財經…
- **公司新聞稿**：Business Wire、PR Newswire、GlobeNewswire（第一手但偏宣傳，情緒權重較低）

同一則新聞被多家轉載時只保留一筆（以標題指紋比對，保留等級最高的來源）。要新增或移除媒體，修改 [`backend/app/services/news_sources.py`](backend/app/services/news_sources.py) 的 `TRUSTED_SOURCES` 即可。

---

## 🧪 測試

```bash
cd backend && pytest -q          # 70 個測試：指標、訊號、情緒、損益、新聞來源解析、API、AI 回應解析
cd frontend && npm run typecheck # TypeScript 型別檢查
cd frontend && npm run build     # 正式版建置
```

測試全部使用 Demo 資料與暫存 SQLite，不需要網路，也不會呼叫付費 API。

---

## 🗂️ 專案結構

```
Stock/
├── backend/                      # Python FastAPI
│   ├── app/
│   │   ├── main.py               # 進入點：路由註冊、CORS、APScheduler 每小時排程
│   │   ├── config.py             # 所有設定（讀 .env）
│   │   ├── db.py / models.py     # 資料庫連線與 ORM 資料表
│   │   ├── schemas.py            # API 輸入驗證 / 輸出格式（Pydantic）
│   │   ├── deps.py               # 目前使用者（Demo 模式；正式版接 JWT）
│   │   ├── routers/              # API：portfolio · watchlist · stocks · jobs
│   │   ├── services/
│   │   │   ├── indicators.py     # MA、RSI、布林通道、ATR
│   │   │   ├── signals.py        # ⭐ 買賣訊號 + Buy Zone / TP / SL
│   │   │   ├── sentiment.py      # ⭐ 中英文新聞情緒分析
│   │   │   ├── llm.py            # Claude AI 摘要（選用）
│   │   │   ├── news.py           # 多來源新聞：Yahoo / Google News / 證交所 / Finnhub
│   │   │   ├── news_sources.py   # 可信媒體白名單與分級
│   │   │   ├── news_pipeline.py  # 抓新聞 → 去重 → 情緒 → 摘要
│   │   │   ├── market_data.py    # yfinance / Demo 行情 + 快取
│   │   │   ├── portfolio.py      # 損益計算公式
│   │   │   └── catalog.py        # 藍籌股清單與簡介
│   │   ├── jobs/hourly_news.py   # ⭐ 每小時排程
│   │   └── check_sources.py      # 連線診斷：python -m app.check_sources
│   └── tests/                    # pytest
├── frontend/                     # Next.js 16 (App Router) + Tailwind v4
│   ├── app/                      # layout.tsx、page.tsx、globals.css（設計 token）
│   ├── components/
│   │   ├── dashboard/
│   │   │   ├── Dashboard.tsx     # ⭐ 主儀表板版面
│   │   │   ├── PortfolioSummary.tsx
│   │   │   ├── HoldingCard.tsx   # ⭐ 持股卡片
│   │   │   ├── HoldingFormDialog.tsx
│   │   │   ├── SignalBadge.tsx   # ⭐ 買進 / 賣出標籤
│   │   │   ├── SignalLevels.tsx  # ⭐ Buy Zone / TP / SL 價位
│   │   │   ├── StarButton.tsx    # ⭐ 收藏按鈕（樂觀更新）
│   │   │   ├── NewsPanel.tsx · SentimentBadge.tsx
│   │   │   └── WatchlistPanel.tsx · Recommendations.tsx · StockCard.tsx
│   │   ├── chart/KLineChart.tsx  # ⭐ K 線圖（價位線、買賣標記、RSI 副圖）
│   │   └── ui/                   # shadcn/ui 風格基礎元件
│   └── lib/                      # api.ts、types.ts、format.ts、market-colors.tsx
├── database/schema.sql           # PostgreSQL Schema
└── docs/                         # 架構、演算法說明
```

---

## 🔐 安全性重點（資安筆記）

這個專案刻意示範了幾個常見的 Web 資安防護，詳細表格見 [`docs/ARCHITECTURE.md` §5](docs/ARCHITECTURE.md#5-安全性設計security-notes)：
輸入白名單驗證、IDOR 防護、排程 API 密鑰 + `compare_digest`、外部連結 XSS 過濾、`rel="noopener noreferrer"`、LLM Prompt Injection 防護、機密只放後端 `.env`、CORS 白名單。

> ⚠️ 目前是**單人模式**，沒有登入功能，請不要直接部署到公開網路。多人使用前請先接上 Supabase Auth / NextAuth（見 `backend/app/deps.py` 的註解）。

---

## ⚠️ 免責聲明

本專案的買賣訊號與 AI 摘要僅供學習與參考，不構成任何投資建議。yfinance 為非官方資料來源，報價可能延遲或中斷；正式使用建議改接 Fugle（台股）或 Finnhub / Alpha Vantage（美股）等官方 API。
