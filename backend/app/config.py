"""
集中管理所有設定（Settings）。

pydantic-settings 會依序從「環境變數」和 backend/.env 讀取設定，
所以 API Key 等機密資料永遠不需要寫死在程式碼裡（資安基本功）。
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── 資料庫 ──────────────────────────────────────────────
    # 本機開發預設用 SQLite（零設定）；正式環境換成 PostgreSQL / Supabase：
    #   postgresql+psycopg://user:password@host:5432/stock
    database_url: str = "sqlite:///./stock.db"

    # ── 市場資料來源 ────────────────────────────────────────
    # "yfinance"：真實行情（需要能連到 Yahoo Finance）
    # "demo"    ：離線假資料（隨機漫步），沒網路也能完整跑起整個 App
    data_provider: Literal["yfinance", "demo"] = "yfinance"

    # 投資組合的「基準幣別」：美股(USD) 與台股(TWD) 會換算成此幣別加總
    base_currency: str = "TWD"

    # ── 安全性 ──────────────────────────────────────────────
    # 允許哪些前端網域呼叫 API（CORS）。不要在正式環境用 "*"。
    cors_origins: list[str] = ["http://localhost:3000"]
    # 手動觸發排程 API 的密鑰；留空 = 停用該 API。
    cron_secret: str = ""
    # 網站密碼保護（部署到網路上時「一定要」設定 APP_PASSWORD）；留空 = 不需要登入
    app_username: str = "admin"
    app_password: str = ""

    # ── 部署 ────────────────────────────────────────────────
    # 前端 build 出來的靜態檔資料夾（Docker 映像檔裡會自動設定）。
    # 有設定時，FastAPI 會同時提供網頁 + API → 整個 App 只需要一個網址。
    static_dir: str | None = None

    # ── 排程（Cron Job）─────────────────────────────────────
    # 是否在 API 伺服器內啟動 APScheduler。
    # 若改用外部 cron（例如 GitHub Actions / Vercel Cron）呼叫 API，就設成 false。
    enable_scheduler: bool = True
    # 每小時第幾分鐘執行（0 = 每小時整點）
    news_refresh_minute: int = 0

    # ── 新聞來源 ────────────────────────────────────────────
    # yahoo  ：Yahoo Finance 個股新聞（免 Key）
    # google ：Google News RSS，只搜尋白名單裡的財經媒體（免 Key）
    # twse   ：證交所 OpenAPI「上市公司每日重大訊息」（官方、免 Key，只適用 .TW）
    # finnhub：Finnhub 公司新聞（需要免費的 FINNHUB_API_KEY，只適用美股）
    news_sources: list[str] = ["yahoo", "google", "twse", "finnhub"]
    # 只保留 services/news_sources.py 白名單裡的可信媒體
    news_trusted_only: bool = True
    finnhub_api_key: str | None = None

    # ── AI 摘要（選用）──────────────────────────────────────
    # 有填 API Key 才會呼叫 Claude 產生摘要；沒填就用內建的規則式摘要。
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"


@lru_cache
def get_settings() -> Settings:
    """用 lru_cache 讓整個程式只建立一次 Settings 物件。"""
    return Settings()
