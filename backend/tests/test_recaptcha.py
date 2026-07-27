"""
Unit tests for app/auth/recaptcha.py — mocked, no real calls to the
reCAPTCHA Enterprise Assessment API (keeps CI free of network flakiness and
off the free-tier assessment quota).
"""
import httpx
import pytest

from app.auth import recaptcha as recaptcha_module
from app.auth.recaptcha import verify_recaptcha


class _FakeResponse:
    def __init__(self, json_body, status_code=200):
        self._json_body = json_body
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json_body


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(recaptcha_module.settings, "RECAPTCHA_API_KEY", "test-api-key")
    monkeypatch.setattr(recaptcha_module.settings, "RECAPTCHA_SITE_KEY", "test-site-key")
    monkeypatch.setattr(recaptcha_module.settings, "RECAPTCHA_PROJECT_ID", "test-project")
    monkeypatch.setattr(recaptcha_module.settings, "RECAPTCHA_MIN_SCORE", 0.5)


def test_skips_verification_when_api_key_not_configured(monkeypatch):
    monkeypatch.setattr(recaptcha_module.settings, "RECAPTCHA_API_KEY", "")
    assert verify_recaptcha("", "login") is True
    assert verify_recaptcha("any-token", "signup") is True


def test_empty_token_rejected_when_configured(configured):
    assert verify_recaptcha("", "login") is False


def test_valid_high_score_token_passes(configured, monkeypatch):
    body = {
        "tokenProperties": {"valid": True, "action": "login"},
        "riskAnalysis": {"score": 0.9},
    }
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: _FakeResponse(body))
    assert verify_recaptcha("good-token", "login") is True


def test_invalid_token_rejected(configured, monkeypatch):
    body = {"tokenProperties": {"valid": False, "invalidReason": "EXPIRED"}}
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: _FakeResponse(body))
    assert verify_recaptcha("expired-token", "login") is False


def test_action_mismatch_rejected(configured, monkeypatch):
    body = {
        "tokenProperties": {"valid": True, "action": "signup"},
        "riskAnalysis": {"score": 0.9},
    }
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: _FakeResponse(body))
    assert verify_recaptcha("mismatched-token", "login") is False


def test_low_score_rejected(configured, monkeypatch):
    body = {
        "tokenProperties": {"valid": True, "action": "login"},
        "riskAnalysis": {"score": 0.1},
    }
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: _FakeResponse(body))
    assert verify_recaptcha("bot-token", "login") is False


def test_assessment_call_failure_fails_open(configured, monkeypatch):
    def _raise(*a, **kw):
        raise httpx.ConnectError("network down")
    monkeypatch.setattr(httpx, "post", _raise)
    assert verify_recaptcha("some-token", "login") is True
