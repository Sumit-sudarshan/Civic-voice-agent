"""
Deterministic validation for structured fields — regex, not the LLM, decides
whether a phone/pincode is well-formed, extending the "LLM proposes, code
disposes" principle to citizen- and leader-supplied form input as well as
extracted fields. Email validation is handled separately by pydantic's
EmailStr wherever an email field is accepted (app/api/auth.py).
"""
import re

# Indian mobile numbers: 10 digits, starting 6-9, optional +91/91 prefix.
PHONE_RE = re.compile(r"^(\+?91[\-\s]?)?[6-9]\d{9}$")

# Indian postal (PIN) codes: exactly 6 digits.
PINCODE_RE = re.compile(r"^\d{6}$")


def validate_phone(value: str) -> str:
    cleaned = value.strip()
    if not PHONE_RE.match(cleaned):
        raise ValueError("Enter a valid 10-digit Indian mobile number.")
    return cleaned


def validate_pincode(value: str) -> str:
    cleaned = value.strip()
    if not PINCODE_RE.match(cleaned):
        raise ValueError("Pincode must be exactly 6 digits.")
    return cleaned


def mask_phone(value: str) -> str:
    """FR12: citizen phone masked by default on the leader dashboard — first
    2 and last 2 digits visible, rest starred out."""
    if not value or len(value) <= 4:
        return "*" * len(value or "")
    return value[:2] + "*" * (len(value) - 4) + value[-2:]
