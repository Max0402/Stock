"""
上線用的安全防護：帳號密碼登入 + 登入失敗限制 + 安全性 HTTP 標頭。

登入方式：HTTP Basic Auth
--------------------------
瀏覽器會跳出帳號密碼視窗，登入後同一個網站的請求（包含前端呼叫 /api 的 fetch）都會自動帶上帳密。
⚠️ Basic Auth 的帳密只是 Base64「編碼」（不是加密），所以一定要走 HTTPS
   （Render、Railway、Fly.io 等平台預設都提供 HTTPS）。

帳號設定（環境變數）
--------------------
    APP_USERNAME=max                 ← 你（網站擁有者）的帳號
    APP_PASSWORD=<隨機長密碼>
    APP_USERS=amy:<密碼>,ben:<密碼>   ← 朋友的帳號（選填，逗號分隔，每組是「帳號:密碼」）

    產生隨機密碼：python -c "import secrets; print(secrets.token_urlsafe(18))"

每個帳號有自己的持股與追蹤清單（見 deps.py）；新聞、K 線等公開資料大家共用。
完全沒有設定任何密碼 = 不需要登入（只適合在自己電腦上開發）。
"""

import base64
import binascii
import logging
import re
import secrets
import threading
import time

from fastapi import Request
from fastapi.responses import PlainTextResponse

from .config import Settings, get_settings

log = logging.getLogger(__name__)

# 不需要登入的路徑：
#   /api/health             雲端平台的健康檢查（只回傳狀態，沒有個人資料）
#   /api/jobs/refresh-news  外部排程呼叫用，它有自己的 X-Cron-Secret 驗證
PUBLIC_PATHS = frozenset({"/api/health", "/api/jobs/refresh-news"})

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",            # 禁止瀏覽器亂猜檔案類型（防 MIME sniffing）
    "X-Frame-Options": "DENY",                      # 禁止被別的網站用 <iframe> 嵌入（防點擊劫持）
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")


# ─────────────────────────── 帳號 ───────────────────────────
def load_accounts(settings: Settings) -> dict[str, str]:
    """把設定整理成 {帳號: 密碼}。格式錯誤的項目會被略過並寫 log（不會讓整個網站掛掉）。"""
    accounts: dict[str, str] = {}
    if settings.app_password:
        accounts[settings.app_username] = settings.app_password
    for entry in filter(None, (e.strip() for e in settings.app_users.split(","))):
        user, sep, pw = entry.partition(":")
        user = user.strip()
        if not sep or not pw or not _USERNAME_RE.match(user):
            log.warning("APP_USERS 有一筆格式錯誤，已略過（正確格式：帳號:密碼）")
            continue
        if user in accounts:
            log.warning("APP_USERS 的帳號 %s 重複，已略過後面那一筆", user)
            continue
        accounts[user] = pw
    return accounts


def authenticate(header: str | None, accounts: dict[str, str]) -> str | None:
    """驗證 Authorization 標頭；成功回傳帳號名稱，失敗回傳 None。"""
    if not header or not header.lower().startswith("basic "):
        return None
    try:
        decoded = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    user, sep, pw = decoded.partition(":")
    if not sep:
        return None
    expected = accounts.get(user)
    # compare_digest：比較時間固定，攻擊者無法從回應快慢一個字一個字猜出密碼（計時攻擊）。
    # 帳號不存在時也照樣比對一次，讓「帳號不存在」和「密碼錯誤」花的時間差不多。
    ok = secrets.compare_digest(pw.encode(), (expected or "\x00no-such-user").encode())
    return user if ok and expected is not None else None


# ─────────────────────── 登入失敗次數限制 ───────────────────────
class LoginThrottle:
    """
    同一個 IP 在 window 秒內密碼錯 max_failures 次 → 暫時封鎖，擋住暴力破解（一直猜密碼）。
    只記錄「有送帳密但錯誤」的請求：瀏覽器第一次開網頁時本來就不會帶帳密，那不算失敗。
    （資料存在記憶體裡，主機重啟就會清空；這對個人網站已經足夠。）
    """

    def __init__(self, max_failures: int = 10, window_seconds: float = 600):
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(key, []) if now - t < self.window]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key, time.monotonic())) >= self.max_failures

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            if len(self._failures) > 10_000:  # 避免被大量假 IP 塞爆記憶體
                self._failures.clear()
            self._failures[key] = [*self._recent(key, now), now]

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


login_throttle = LoginThrottle()


def _unauthorized(message: str, status: int, extra: dict | None = None) -> PlainTextResponse:
    headers = {**SECURITY_HEADERS, **(extra or {})}
    if status == 401:
        headers["WWW-Authenticate"] = 'Basic realm="Stock Tracker", charset="UTF-8"'
    return PlainTextResponse(message, status_code=status, headers=headers)


async def security_middleware(request: Request, call_next):
    accounts = load_accounts(get_settings())
    request.state.username = None

    if accounts and request.url.path not in PUBLIC_PATHS:
        client_ip = request.client.host if request.client else "unknown"
        if login_throttle.is_blocked(client_ip):
            return _unauthorized("嘗試次數過多，請 10 分鐘後再試 / Too many attempts", 429, {"Retry-After": "600"})

        header = request.headers.get("authorization")
        username = authenticate(header, accounts)
        if username is None:
            if header:  # 有送帳密但錯誤才算一次失敗
                login_throttle.record_failure(client_ip)
            return _unauthorized("需要登入 / Authentication required", 401)
        login_throttle.reset(client_ip)
        request.state.username = username  # deps.get_current_user 會用這個找出「是誰」

    response = await call_next(request)
    for key, value in SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)
    # 雲端平台會在前面幫忙處理 HTTPS，並用 X-Forwarded-Proto 告訴我們原本是 https
    if request.headers.get("x-forwarded-proto") == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")  # 之後一律走 HTTPS
    return response
