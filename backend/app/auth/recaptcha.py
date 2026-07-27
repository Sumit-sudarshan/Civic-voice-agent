"""
reCAPTCHA Enterprise verification (score-based / v3-equivalent), used on
citizen and leader signup + login — see MVP_Design.md §3.1/§5 and the Phase 4
roadmap entry this replaces (classic reCAPTCHA v3 was skipped there because it
needs manual per-domain registration at a Google-account-tied web console;
reCAPTCHA Enterprise is created and managed via `gcloud recaptcha`/`gcloud
services api-keys`, which is what's wired up here).

The site key's domain allowlist is registered as "trycloudflare.com" (not the
specific random quick-tunnel subdomain), so a tunnel restart never breaks
verification — Google's domain matching auto-allows all subdomains.
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_ASSESSMENT_URL = "https://recaptchaenterprise.googleapis.com/v1/projects/{project}/assessments"


def verify_recaptcha(token: str, expected_action: str) -> bool:
    """
    Returns True if the token is valid, matches expected_action, and scores
    above RECAPTCHA_MIN_SCORE. If RECAPTCHA_API_KEY is unset (local dev/CI
    without the secret configured), verification is skipped and this returns
    True — same graceful-degrade pattern as HF_TOKEN elsewhere in this app.
    """
    if not settings.RECAPTCHA_API_KEY:
        logger.warning("RECAPTCHA_API_KEY not configured — skipping reCAPTCHA verification")
        return True

    if not token:
        return False

    url = _ASSESSMENT_URL.format(project=settings.RECAPTCHA_PROJECT_ID)
    body = {
        "event": {
            "token": token,
            "expectedAction": expected_action,
            "siteKey": settings.RECAPTCHA_SITE_KEY,
        }
    }
    try:
        resp = httpx.post(url, params={"key": settings.RECAPTCHA_API_KEY}, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        # A verification-service outage should not be indistinguishable from
        # a bot — but it also shouldn't lock out every real user. Logged loud,
        # fails open, same trade-off as the missing-API-key case above.
        logger.error(f"reCAPTCHA assessment call failed: {e}")
        return True

    token_props = data.get("tokenProperties", {})
    if not token_props.get("valid"):
        logger.warning(f"reCAPTCHA token invalid: {token_props.get('invalidReason')}")
        return False
    if token_props.get("action") != expected_action:
        logger.warning(f"reCAPTCHA action mismatch: expected {expected_action}, got {token_props.get('action')}")
        return False

    score = data.get("riskAnalysis", {}).get("score", 0.0)
    if score < settings.RECAPTCHA_MIN_SCORE:
        logger.warning(f"reCAPTCHA score {score} below threshold {settings.RECAPTCHA_MIN_SCORE}")
        return False
    return True
