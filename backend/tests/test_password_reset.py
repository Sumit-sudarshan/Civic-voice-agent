"""
Tests for the /auth/forgot-password and /auth/reset-password endpoints —
mocked at the httpx call boundary, no real Supabase GoTrue traffic.
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api import auth as auth_module

client = TestClient(app)


class _FakeResponse:
    def __init__(self, json_body, status_code=200):
        self._json_body = json_body
        self.status_code = status_code

    def json(self):
        return self._json_body


@pytest.fixture(autouse=True)
def _skip_recaptcha(monkeypatch):
    # Only exercising the Supabase-proxy behavior here — reCAPTCHA itself is
    # covered by test_recaptcha.py.
    monkeypatch.setattr(auth_module, "verify_recaptcha", lambda token, action: True)


def test_forgot_password_calls_supabase_recover_with_redirect_from_origin(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, params=None, json=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["json"] = json
        return _FakeResponse({})

    monkeypatch.setattr(httpx, "post", fake_post)

    resp = client.post(
        "/auth/forgot-password",
        json={"email": "citizen@example.com"},
        headers={"origin": "https://approve-videos-webcams-directories.trycloudflare.com"},
    )

    assert resp.status_code == 200
    assert "sent" in resp.json()["message"].lower()
    assert captured["url"].endswith("/recover")
    assert captured["json"] == {"email": "citizen@example.com"}
    assert captured["params"]["redirect_to"] == "https://approve-videos-webcams-directories.trycloudflare.com/reset-password"


def test_forgot_password_without_origin_omits_redirect(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, params=None, json=None, timeout=None):
        captured["params"] = params
        return _FakeResponse({})

    monkeypatch.setattr(httpx, "post", fake_post)

    resp = client.post("/auth/forgot-password", json={"email": "citizen@example.com"})

    assert resp.status_code == 200
    assert captured["params"] == {}


def test_forgot_password_surfaces_supabase_error(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: _FakeResponse({"msg": "rate limited"}, status_code=429))

    resp = client.post("/auth/forgot-password", json={"email": "citizen@example.com"})

    assert resp.status_code == 400


def test_reset_password_success(monkeypatch):
    captured = {}

    def fake_put(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _FakeResponse({})

    monkeypatch.setattr(httpx, "put", fake_put)

    resp = client.post(
        "/auth/reset-password",
        json={"access_token": "recovery-jwt", "new_password": "newpassword123"},
    )

    assert resp.status_code == 200
    assert "updated" in resp.json()["message"].lower()
    assert captured["url"].endswith("/user")
    assert captured["headers"]["Authorization"] == "Bearer recovery-jwt"
    assert captured["json"] == {"password": "newpassword123"}


def test_reset_password_rejects_expired_token(monkeypatch):
    monkeypatch.setattr(httpx, "put", lambda *a, **kw: _FakeResponse({"msg": "token expired"}, status_code=401))

    resp = client.post(
        "/auth/reset-password",
        json={"access_token": "expired-jwt", "new_password": "newpassword123"},
    )

    assert resp.status_code == 400
