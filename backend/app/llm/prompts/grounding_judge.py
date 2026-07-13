"""
Grounded faithfulness judge for the leader briefing (eval Layer 5).

In our architecture render_report builds the briefing's numbers/sections
deterministically from the facts dict — the ONE genuinely model-written part is
the closing verdict sentence. So the hallucination surface for the summary is
that verdict, and this judge is aimed squarely at it: given the authoritative
facts and the verdict the model wrote, it flags any claim the facts don't
support (an invented number, place, category, or a trend that contradicts the
data). Opinion/tone ("worth escalating") is fine as long as the direction is
consistent with the stats.

The numeric- and location-accuracy metrics are checked deterministically in the
eval script (they compare the rendered text against the facts directly, no LLM
needed) — this module only covers the free-text judgement call.
"""
from typing import List
from pydantic import BaseModel, Field


class VerdictGrounding(BaseModel):
    unsupported_claims: List[str] = Field(
        default_factory=list,
        description="Every factual claim in the verdict that the source statistics do NOT support "
                    "(an invented/incorrect number, a place or category not in the stats, or a trend that "
                    "contradicts the numbers). Empty list if the verdict is fully supported.",
    )
    faithful: bool = Field(
        ..., description="True if the verdict makes no claim unsupported by the source statistics."
    )


GROUNDING_SYSTEM_PROMPT = """You are a fact-checker for the one-line verdict printed at the bottom of a
civic-issues briefing. You are given (A) the AUTHORITATIVE statistics the briefing was built from, and
(B) the verdict sentence a model wrote. Treat A as the only source of truth — use no outside knowledge.

The verdict's JOB is to give a subjective judgement of the period, so most of it is opinion, not fact.
Flag ONLY a hard, checkable factual error — specifically:
  * a specific NUMBER stated in B that is not in A or disagrees with A, or
  * a specific PLACE/AREA or CATEGORY named in B that does not appear in A, or
  * a claim that directly CONTRADICTS A (e.g. "no critical issues" when A lists critical items, or
    "cases are falling" when A shows they rose).

DO NOT FLAG (these are allowed judgement, never hallucinations):
  * tone or volume words — "quiet", "calm", "busy", "a quiet start", "limited data", "notable",
    "manageable", "worth watching", "worsening", "worth escalating", "normal";
  * vague, unquantified statements that name no specific wrong number, place, or category;
  * hedging like "difficult to draw conclusions" or "limited data".

Only flag a claim if you can point to the exact number/place/category in B that A does not support.
When unsure, do NOT flag it. If nothing qualifies, return an empty list and faithful=true.

Each item in unsupported_claims must be a short PLAIN-TEXT STRING quoting the offending phrase (e.g.
"40 critical cases"), never an object. Respond with the structured fields only.
"""


def build_grounding_user_prompt(facts_summary: str, verdict: str) -> str:
    return (
        "SOURCE STATISTICS (authoritative — the only truth):\n"
        f"{facts_summary}\n\n"
        "VERDICT SENTENCE TO CHECK:\n"
        f'"{verdict}"\n\n'
        "List any claim in the verdict not supported by the statistics above."
    )
