"""密碼保護（HTTP Basic Auth）與安全性標頭。"""

import base64

import pytest
from fastapi.testclient import TestClient

from app import security
from app.config import get_settings
from app.db import normalize_db_url
from app.main import app


def _basic(user: str, pw: str) -> dict:
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}


@pytest.fixture
def locked_client(monkeypatch):
    s = get_settings().model_copy(update={"app_username": "max", "app_password": "correct-horse-battery"})
    monkeypatch.setattr(security, "get_settings", lambda: s)
    with TestClient(app) as c:
        yield c


def test_requires_password(locked_client):
    r = locked_client.get("/api/portfolio")
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Basic")


@pytest.mark.parametrize(
    "headers",
    [
        _basic("max", "wrong"),
        _basic("someone", "correct-horse-battery"),
        {"Authorization": "Basic !!!not-base64!!!"},
        {"Authorization": "Bearer correct-horse-battery"},
        {"Authorization": "Basic " + base64.b64encode(b"no-colon").decode()},
    ],
)
def test_rejects_bad_credentials(locked_client, headers):
    assert locked_client.get("/api/portfolio", headers=headers).status_code == 401


def test_accepts_correct_credentials(locked_client):
    r = locked_client.get("/api/portfolio", headers=_basic("max", "correct-horse-battery"))
    assert r.status_code == 200


def test_public_paths_stay_open(locked_client):
    assert locked_client.get("/api/health").status_code == 200
    # 排程 API 不用網站密碼，但仍需要它自己的 X-Cron-Secret
    assert locked_client.post("/api/jobs/refresh-news").status_code == 401
    assert locked_client.post("/api/jobs/refresh-news", headers={"X-Cron-Secret": "test-secret"}).status_code == 200


def test_security_headers_present(locked_client):
    r = locked_client.get("/api/health", headers={"X-Forwarded-Proto": "https"})
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "max-age" in r.headers["strict-transport-security"]


def test_no_password_means_open():
    with TestClient(app) as c:  # 測試環境沒有設定 APP_PASSWORD
        assert c.get("/api/portfolio").status_code == 200


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("postgres://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("postgresql://u:p@ep-x.neon.tech/db?sslmode=require", "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=require"),
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("sqlite:///./stock.db", "sqlite:///./stock.db"),
    ],
)
def test_normalize_db_url(raw, expected):
    assert normalize_db_url(raw) == expected
