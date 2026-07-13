"""
Cheap, LLM-free language identification (Roadmap Phase 14) — runs before any
LLM call so `language_detected` is populated for logging/analytics even if
every downstream stage later fails.

This value is NEVER used to branch pipeline logic: gatekeeper/classify/
urgency/extract all run the same code path regardless of what's detected
here. The prompts themselves (see llm/prompts/*.py) tell the LLM to expect
Hindi/Marathi/English/Hinglish directly, so a wrong guess here doesn't break
the pipeline — it only makes the analytics/dashboard label less accurate.

Known limitation: `langdetect` classifies by script/statistics trained on
"pure" language samples, so Hinglish (Hindi content transliterated into Latin
script) doesn't cleanly match any of its models. Empirically (see
tests/test_language.py), plain `detect()` misclassified real Hinglish sample
text as Indonesian ('id') — not just imprecise, actively wrong, since
Indonesian/Malay/Tagalog share many short Latin-script words with English and
regularly win this kind of statistical race. Since this product only ever
expects English, Hindi, or Marathi (plus Hinglish, which is English-scripted),
we use `detect_langs()`'s full probability ranking and pick the best-scoring
candidate AMONG THOSE THREE specifically, rather than trusting the unconstrained
top guess — a deliberate, documented use of domain knowledge, not a general
language identifier. This is still just for logging/analytics, never for
branching pipeline logic.
"""
import logging
from langdetect import detect_langs, LangDetectException

logger = logging.getLogger(__name__)

_EXPECTED_LANGUAGES = {"en", "hi", "mr"}


def detect_language(text: str) -> str:
    """Returns 'hi', 'mr', or 'en' — the highest-probability match among the
    three languages this product actually expects. Falls back to 'en' if
    detection fails outright (e.g. very short/numeric-only text) or if none
    of the three appear anywhere in langdetect's ranked candidates."""
    if not text or not text.strip():
        return "en"
    try:
        candidates = detect_langs(text)
    except LangDetectException as e:
        logger.warning(f"Language detection failed, defaulting to 'en': {e}")
        return "en"

    for candidate in candidates:  # already sorted by probability, descending
        if candidate.lang in _EXPECTED_LANGUAGES:
            return candidate.lang
    return "en"
