"""
Deterministic, no-LLM substitute for the dialogue-manager stage, used only
when `run_dialogue_manager()` itself fails (timeout, rate limit, malformed
response — see orchestrator._prepare_turn).

The bug this replaces: the previous fallback was a blind constant,
`DialogueState(issue_clear=False)`, regardless of what the citizen actually
wrote. Combined with vagueness_mode (also forced on whenever the gatekeeper
call fails), a citizen who submitted several detailed sentences in one
message — location, landmark, duration, impact — was still asked "could you
describe the issue in a bit more detail?", purely because the LLM was down,
not because anything was genuinely missing. That is a visible, avoidable
"this system is obviously broken" moment during exactly the kind of outage
this fallback path exists to survive gracefully.

This does not attempt the dialogue manager's actual precision — no
area/address disambiguation, no landmark-vs-area judgment calls, all of
which need real language understanding to get right. It only prevents the
fallback from re-asking a citizen for something they already, plainly gave,
using cheap, honest, explainable signals. Anything this heuristic misses
just costs one extra question, which is the safe direction to be wrong in
(the same principle decide_next_action already applies to the dialogue
manager's own real judgments — see its docstring).
"""
import re
from typing import Optional

from app.llm.prompts.dialogue import DialogueState

_PINCODE_RE = re.compile(r"\b(\d{6})\b")

# Phrases that typically introduce a landmark or specific spot — "near the
# water tank", "opposite the school", etc. Presence of any of these is a
# strong, cheap signal that the citizen already gave locating detail, even
# though we can't (without an LLM) separate it cleanly into address vs. area.
_LANDMARK_MARKERS = (
    "near ", "opposite ", "behind ", "next to ", "in front of ", "beside ",
    "adjacent to ", "close to ", "front of ",
)

# Common place-noun words that show up in an Indian colony/locality name or
# address, independent of language register — another cheap, honest signal.
_PLACE_NOUNS = (
    "colony", "nagar", "society", "sector", "chowk", "chawl", "gali",
    "basti", "layout", "apartment", "building", "complex", "block", "vasahat",
)

# Below this many words from the citizen, the message is short enough that a
# real clarifying question is still warranted — matches the kind of input
# EXAMPLE 5 in dialogue.py's few-shot prompt calls genuinely vague ("There's
# a problem in my area, please fix it." is 8 words). At or above it, the
# safer assumption during an outage is that there's real substance already
# worth acting on rather than re-interrogating the citizen.
_MIN_WORDS_FOR_CLEAR_ISSUE = 9


def _citizen_text(transcript_blob: str) -> str:
    """Only the citizen's own lines — an Agent's question shouldn't inflate
    the perceived amount of detail given."""
    lines = [
        line.split(":", 1)[1].strip()
        for line in transcript_blob.splitlines()
        if line.startswith("Citizen:") and ":" in line
    ]
    return " ".join(lines)


def _extract_pincode(text: str) -> Optional[str]:
    match = _PINCODE_RE.search(text)
    return match.group(1) if match else None


def _extract_address_hint(text: str) -> Optional[str]:
    lowered = text.lower()
    has_marker = any(marker in lowered for marker in _LANDMARK_MARKERS)
    has_noun = any(noun in lowered for noun in _PLACE_NOUNS)
    if has_marker or has_noun:
        return text.strip()
    return None


def build_fallback_dialogue_state(transcript_blob: str) -> DialogueState:
    """Read the transcript directly instead of assuming nothing is known."""
    text = _citizen_text(transcript_blob)
    word_count = len(text.split())
    address_hint = _extract_address_hint(text)
    pincode = _extract_pincode(text)

    return DialogueState(
        location_address=address_hint,
        address_specific_enough=address_hint is not None,
        location_area=None,  # never guessed — a wrong area is worse than one more question
        location_pincode=pincode,
        pincode_declined=False,
        issue_clear=word_count >= _MIN_WORDS_FOR_CLEAR_ISSUE,
        issue_clarity_reason=(
            f"Deterministic fallback judgment (dialogue-manager LLM call failed): "
            f"{word_count} word(s) from the citizen so far, "
            f"{'threshold met' if word_count >= _MIN_WORDS_FOR_CLEAR_ISSUE else 'below threshold'}."
        ),
    )
