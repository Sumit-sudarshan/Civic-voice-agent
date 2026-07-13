"""
LLM-as-judge for extraction quality (eval Layer 3).

This is the automated counterpart to the manual human rubric in
eval/score_extraction.py. To be a *validated* proxy rather than "the LLM
grading its own homework", the judge is deliberately built to be checkable and
comparable:

1. It scores the SAME four fields (location, issue_summary, affected_parties,
   ask) on the SAME 1-5 rubric a human uses in score_extraction.py — so the two
   score sets can be compared field-by-field and the judge validated against the
   19 real human scores already on disk.
2. It is GROUNDED: it sees only the citizen's raw_text plus the extraction under
   review. It is never given a "correct answer" (none exists — there's no single
   right phrasing), so it must reason from the source text, exactly like the
   human reviewer does.
3. Each field's rubric is written in checkable terms (faithfulness / no
   invention / concrete-actionable-ask / no verbatim dumping) so a score is a
   judgment about specific properties, not a vague "is this good?".

A separate, model-free verbatim-copy metric (string overlap between
issue_summary and raw_text) lives in the eval script, not here — it needs no LLM.
"""
from typing import Optional
from pydantic import BaseModel, Field


class ExtractionJudgment(BaseModel):
    """Per-field 1-5 quality scores, on the same scale as the human rubric in
    score_extraction.py, plus a one-line reason each so a score is auditable."""
    location_score: int = Field(
        ..., ge=1, le=5,
        description="1-5 quality of the extracted location (see rubric). 5 = accurately reflects the "
                    "location the text states/implies with no invented places; 1 = wrong or invented."
    )
    location_reason: Optional[str] = Field(None, description="One short sentence justifying the location score.")

    issue_summary_score: int = Field(
        ..., ge=1, le=5,
        description="1-5 quality of issue_summary. 5 = faithful to the text, concise, captures the core "
                    "problem, invents nothing and does NOT just copy the raw text verbatim; "
                    "1 = wrong, invented, or an unedited dump of the input."
    )
    issue_summary_reason: Optional[str] = Field(None, description="One short sentence justifying the summary score.")

    affected_parties_score: int = Field(
        ..., ge=1, le=5,
        description="1-5 quality of affected_parties. 5 = specific and genuinely supported by the text or "
                    "the location/category context, not a lazy catch-all; 1 = invented a group the text "
                    "doesn't support, or wrongly vague."
    )
    affected_parties_reason: Optional[str] = Field(None, description="One short sentence justifying the affected-parties score.")

    ask_score: int = Field(
        ..., ge=1, le=5,
        description="1-5 quality of ask. 5 = a concrete, actionable instruction a staffer could act on, "
                    "correctly matching the issue; 1 = vague, wrong, or not an action at all."
    )
    ask_reason: Optional[str] = Field(None, description="One short sentence justifying the ask score.")


JUDGE_SYSTEM_PROMPT = """You are a strict, fair quality reviewer for a civic-complaint data-extraction system.
You are given a citizen's ORIGINAL text and the four fields an extraction model produced from it
(location, issue_summary, affected_parties, ask). Judge how good each extracted field is, using ONLY
the original text as your source of truth. You are NOT given a reference answer because there is no
single correct phrasing — reason from the original text the same way a careful human reviewer would.

Score each of the four fields from 1 to 5 on this rubric:
  5 = Fully correct, captures exactly what's in the text, no invention.
  4 = Correct and usable, minor phrasing awkwardness only.
  3 = Mostly correct but missing a detail a leader would want.
  2 = Partially wrong or vague enough to be unhelpful.
  1 = Wrong, or invented information not present in the original text.

Apply these field-specific checks when scoring:
- location: does it reflect the place the text actually states or clearly implies? Penalise invented
  streets/areas. "not specified" is CORRECT (not a low score) when the text genuinely gives no location.
- issue_summary: is every claim in it supported by the text (no invention)? Is it concise? Penalise a
  summary that just copies the raw text back verbatim instead of distilling it.
- affected_parties: is the named group actually supported by the text or the location/category context?
  A specific, supported group scores high; an invented group, or a lazy "everyone/the public" when a
  narrower group was derivable, scores lower.
- ask: is it a concrete action a staffer could actually carry out, and does it match the issue? A vague
  non-action scores low even if politely worded.

Be honest and calibrated — do not inflate scores. Ignore the citizen's tone/rudeness entirely; it must
not affect any score. Respond with the structured fields only.
"""


def build_judge_user_prompt(raw_text: str, location: str, issue_summary: str,
                            affected_parties: str, ask: str) -> str:
    return (
        f'ORIGINAL CITIZEN TEXT:\n"{raw_text}"\n\n'
        f'EXTRACTION TO JUDGE:\n'
        f'- location: "{location}"\n'
        f'- issue_summary: "{issue_summary}"\n'
        f'- affected_parties: "{affected_parties}"\n'
        f'- ask: "{ask}"\n\n'
        f'Score each field 1-5 with a one-line reason, per the rubric.'
    )
