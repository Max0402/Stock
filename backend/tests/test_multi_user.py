"""多人帳號：每個人只能看到、修改自己的資料；登入失敗次數限制。"""

import base64

import pytest
from fastapi.testclient import TestClient

from app import deps, security
from app.config import get_settings
from app.main import app
from app.security import LoginThrottle, load_accounts

PW = {"max": "owner-password-123", "amy": "amy-password-4567", "ben": "ben-password-8901"}


def auth(user: str, pw: str | None = None) -> dict:
    token = base64.b64encode(f"{user}:{pw or PW[user]}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def client(monkeypatch):
    s = get_settings().model_copy(update={
        "app_username": "max", "app_password": PW["max"],
        "app_users": f"amy:{PW['amy']}, ben:{PW['ben']}",
    })
    monkeypatch.setattr(security, "get_settings", lambda: s)
    monkeypatch.setattr(deps, "get_settings", lambda: s)
    monkeypatch.setattr(security, "login_throttle", LoginThrottle(max_failures=3, window_seconds=600))
    with TestClient(app) as c:
        yield c


def test_load_accounts_parsing():
    s = get_settings().model_copy(update={
        "app_username": "max", "app_password": "pw-owner",
        "app_users": "amy:pw:with:colons, bad entry ,:nouser, ben:, ok_user:x, amy:dup",
    })
    accounts = load_accounts(s)
    assert accounts == {"max": "pw-owner", "amy": "pw:with:colons", "ok_user": "x"}


def test_each_user_sees_only_their_own_holdings(client):
    r = client.post("/api/holdings", json={"symbol": "AMZN", "shares": 3, "buy_price": 200}, headers=auth("amy"))
    assert r.status_code == 201
    amy_holding = r.json()["id"]
    client.post("/api/holdings", json={"symbol": "GOOGL", "shares": 5, "buy_price": 150}, headers=auth("ben"))

    amy = [h["symbol"] for h in client.get("/api/portfolio", headers=auth("amy")).json()["holdings"]]
    ben = [h["symbol"] for h in client.get("/api/portfolio", headers=auth("ben")).json()["holdings"]]
    assert amy == ["AMZN"] and ben == ["GOOGL"]

    # IDOR：Ben 知道 Amy 那筆持股的 id，也不能修改或刪除
    assert client.patch(f"/api/holdings/{amy_holding}", json={"shares": 1}, headers=auth("ben")).status_code == 404
    assert client.delete(f"/api/holdings/{amy_holding}", headers=auth("ben")).status_code == 404
    assert client.get("/api/portfolio", headers=auth("amy")).json()["holdings"][0]["shares"] == 3


def test_watchlists_are_separate(client):
    client.post("/api/watchlist", json={"symbol": "TSLA"}, headers=auth("amy"))
    assert [w["symbol"] for w in client.get("/api/watchlist", headers=auth("amy")).json()] == ["TSLA"]
    assert client.get("/api/watchlist", headers=auth("ben")).json() == []


def test_owner_keeps_original_account(client):
    """擁有者登入後用的是原本單人模式那個帳號 → 升級前輸入的資料不會不見。"""
    from app.db import SessionLocal

    with SessionLocal() as db:
        original = deps.ensure_demo_user(db).id
        assert deps.user_for_username(db, "max").id == original
        assert deps.user_for_username(db, None).id == original
        assert deps.user_for_username(db, "amy").id != original


def test_me_endpoint(client):
    assert client.get("/api/me", headers=auth("amy")).json() == {"username": "amy"}
    assert client.get("/api/me").status_code == 401


def test_wrong_passwords_get_throttled(client):
    for _ in range(3):
        assert client.get("/api/portfolio", headers=auth("amy", "guess")).status_code == 401
    # 第 4 次：就算這次密碼正確也先擋下（不讓攻擊者知道剛剛猜對了）
    r = client.get("/api/portfolio", headers=auth("amy"))
    assert r.status_code == 429 and r.headers["retry-after"] == "600"


def test_missing_credentials_do_not_count_as_failures(client):
    for _ in range(5):  # 瀏覽器第一次開網頁本來就不帶帳密 → 不應該被封鎖
        assert client.get("/api/portfolio").status_code == 401
    assert client.get("/api/portfolio", headers=auth("amy")).status_code == 200


def test_throttle_window_expires():
    t = LoginThrottle(max_failures=2, window_seconds=0.05)
    t.record_failure("1.2.3.4")
    t.record_failure("1.2.3.4")
    assert t.is_blocked("1.2.3.4") and not t.is_blocked("5.6.7.8")
    import time
    time.sleep(0.06)
    assert not t.is_blocked("1.2.3.4")
