"""
上線用的安全防護：密碼保護 + 安全性 HTTP 標頭。

為什麼一定要有密碼？
--------------------
這個 App 沒有使用者系統。部署到網路上之後，任何拿到網址的人都能看到、甚至修改你的持股。
最簡單又可靠的做法是 HTTP Basic Auth：瀏覽器會跳出帳號密碼視窗，登入後同一個網站的請求
（包含前端呼叫 /api 的 fetch）都會自動帶上帳密。

⚠️ Basic Auth 的帳密只是 Base64「編碼」（不是加密），所以一定要走 HTTPS。
   Render、Railway、Fly.io 等平台預設都提供 HTTPS。

設定方式（環境變數）：
    APP_USERNAME=max
    APP_PASSWORD=<一組夠長的隨機密碼>
    （產生方式：python -c "import secrets; print(secrets.token_urlsafe(24))"）
APP_PASSWORD 留空 = 不啟用密碼（只適合在自己電腦上開發）。
"""

import base64
import binascii
import secrets

from fastapi import Request
from fastapi.responses import PlainTextResponse

from .config import get_settings

# 不需要密碼的路徑：
#   /api/health          雲端平台的健康檢查（只回傳狀態，沒有個人資料）
#   /api/jobs/refresh-news  外部排程呼叫用，它有自己的 X-Cron-Secret 驗證
PUBLIC_PATHS = frozenset({"/api/health", "/api/jobs/refresh-news"})

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",            # 禁止瀏覽器亂猜檔案類型（防 MIME sniffing）
    "X-Frame-Options": "DENY",                      # 禁止被別的網站用 <iframe> 嵌入（防點擊劫持）
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def check_basic_auth(header: str | None, username: str, password: str) -> bool:
    if not header or not header.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    user, sep, pw = decoded.partition(":")
    if not sep:
        return False
    # compare_digest：比較時間固定，攻擊者無法從回應快慢一個字一個字猜出密碼（計時攻擊）
    # 帳號和密碼「兩個都比完」才回傳，避免從時間差判斷出帳號是否正確
    ok_user = secrets.compare_digest(user.encode(), username.encode())
    ok_pw = secrets.compare_digest(pw.encode(), password.encode())
    return ok_user and ok_pw


async def security_middleware(request: Request, call_next):
    settings = get_settings()
    needs_auth = bool(settings.app_password) and request.url.path not in PUBLIC_PATHS

    if needs_auth and not check_basic_auth(
        request.headers.get("authorization"), settings.app_username, settings.app_password
    ):
        return PlainTextResponse(
            "需要登入 / Authentication required",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Stock Tracker", charset="UTF-8"', **SECURITY_HEADERS},
        )

    response = await call_next(request)
    for key, value in SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)
    # 雲端平台會在前面幫忙處理 HTTPS，並用 X-Forwarded-Proto 告訴我們原本是 https
    if request.headers.get("x-forwarded-proto") == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")  # 之後一律走 HTTPS
    return response
