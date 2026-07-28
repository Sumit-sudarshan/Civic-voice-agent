from typing import Optional
from pydantic import BaseModel, Field

class DialogueState(BaseModel):
    """
    Diagnostic judgment over the conversation so far. This model does NOT
    author citizen-facing question text — a separate stage (compose_reply.py)
    does that once orchestrator.decide_next_action has decided WHICH single
    thing is still missing. Keeping this stage's job narrow (judge state
    only) makes it easier to get right and easier to unit-test against.
    """
    location_address: Optional[str] = Field(
        None, description="Colony/locality name plus any nearby landmark the citizen has given, "
                           "e.g. 'Rajiv Nagar, near Shivaji building'. None if not given yet."
    )
    address_specific_enough: bool = Field(
        False, description="True only if location_address would let someone unfamiliar with the area "
                            "actually find the spot (a colony/locality name, ideally with a landmark). "
                            "False for anything too broad to pinpoint, e.g. just a city or district name."
    )
    location_area: Optional[str] = Field(
        None, description="The broader area/neighbourhood name the address sits inside, when the citizen "
                           "has named one that is genuinely a different, larger place than "
                           "location_address. None if they have not named one yet. Do NOT copy "
                           "location_address's text here, and do NOT invent one — but see "
                           "area_same_as_address for the very common case where the citizen tells us "
                           "there ISN'T a separate broader area, which is an answer, not a missing field."
    )
    area_same_as_address: bool = Field(
        False, description="True when the citizen has effectively told us there is no separate broader "
                            "area to give — because the locality they named IS the area ('Shriram Nagar "
                            "is the area'), because they've repeated the same answer when re-asked, or "
                            "because they've said that's all they know / no further clarification is "
                            "needed. This is a real ANSWER, not a failure to answer: the citizen knows "
                            "their own location better than we do, and many small towns and localities "
                            "genuinely have no larger named neighbourhood above them. Set this True "
                            "rather than leaving the conversation stuck re-asking. False only while the "
                            "area question genuinely hasn't been engaged with yet."
    )
    location_pincode: Optional[str] = Field(
        None, description="The 6-digit PIN code, ONLY if the citizen has literally stated a 6-digit "
                           "number as their PIN code. Set to the literal string 'not specified' and "
                           "pincode_declined=true only if they were asked and explicitly said they "
                           "don't know it. Leave as None (not 'not specified') if pincode simply hasn't "
                           "come up in the conversation at all yet — never guess or invent a number."
    )
    pincode_declined: bool = Field(
        False, description="True ONLY if the citizen was actually asked about the pincode (an Agent "
                            "turn asking for it exists in the transcript) and explicitly said they "
                            "don't know it or declined. False if pincode was never asked about yet."
    )
    issue_clear: bool = Field(
        ..., description="True if the specific issue is concrete enough to act on (what's wrong, "
                          "specifically) — e.g. 'water blockage on MG road' is clear. False for vague "
                          "statements like 'there's a problem' or 'fix it' with no specifics at all."
    )
    issue_clarity_reason: Optional[str] = Field(
        None, description="One short internal note on why issue_clear was judged true/false. Never "
                           "shown to the citizen."
    )


DIALOGUE_SYSTEM_PROMPT = """You judge what a civic-complaint conversation has established so far.
You do NOT write questions or any citizen-facing text — only the structured judgment. Your output
decides whether the citizen is asked another question or their complaint is filed, so every
unnecessary question is a real cost: make someone answer the same thing three ways and they give up.

GOVERNING PRINCIPLE — THE CITIZEN IS THE AUTHORITY ON THEIR OWN LOCATION.
They live there; you do not. When they tell you what their location is, or that what they gave is
all there is, that is a fact to accept, not a claim to second-guess. Both directions matter:
never invent a place name they didn't say, and never refuse an answer just because it isn't the
shape you expected. Someone who answers the same way twice is telling you their answer won't
change — record it and move on.

READING: the transcript is always English (Hindi/Marathi already translated). Read ALL of it, not
just the last line — earlier turns often hold the address/area/pincode/issue. A short reply
("431401", "near the temple") must be read against the Agent question just before it. A leading
"[Context: ...]" line is a city/pincode the citizen typed in a form BEFORE the chat: a pincode
there is already resolved (never re-ask), and the city there is NOT an area — never copy it into
location_area.

FIELDS:
- location_address — the specific place (colony/locality/street/building, ideally with a
  landmark). address_specific_enough=true once a stranger could find it; false for answers naming
  nowhere ("my area", "here", "nearby").
- location_area — a LARGER separately-named neighbourhood containing the address, when the
  citizen has named one. Many places have no such larger unit at all: small towns, standalone
  colonies and villages often go straight from locality to city. Having none is a complete
  answer, not a gap.
- area_same_as_address — set TRUE when the citizen has indicated there is no separate broader
  area. This is the key field for not trapping people in a loop. Set it when they: say the
  locality IS the area ("area is same as X", "X is the area itself"); say that's all they know /
  no further clarification needed / that they already answered; re-answer with the same place
  they already gave; or give a landmark/descriptive answer a SECOND time after the area question
  was already asked once (the first such answer may be a misunderstanding — the second is them
  telling you it's the most precise thing they have).
  When TRUE, leave location_area null — the system falls back to the address itself. Do not copy
  the address into location_area.
  The real question is not "address vs area" but "has the citizen engaged with the area question
  yet?" Not engaged → leave null/false so it gets asked once. Engaged, in any of the ways above →
  settled; move on.
- location_pincode — a 6-digit number only if literally stated (or from [Context]). If asked and
  they don't know: the literal string "not specified" AND pincode_declined=true. If it never came
  up: null, not "not specified". Never invent one.
- issue_clear — true when the problem is concrete enough to act on ("daily 2-3 hour power cuts",
  "garbage uncollected two weeks"); false for "there's a problem, fix it". A vague location does
  not make a clear issue unclear.

NORMALIZING (so two reports of one place group together, not split into variants): strip trailing
filler — "Area", "Zone", "Locality", "Region", "Part" — unless genuinely part of the name
("Sector 15", "Ganesh Colony", "Shastri Nagar"); Title Case; trim whitespace. Apply to address
and area. Clean up filler/casing only — never translate, expand, or "correct" the name given.

NEVER INVENT: every place name you output must appear in the transcript. Names in the examples
below are throwaway illustrations of reasoning, NOT real places — echoing one the citizen never
said files their complaint against the wrong location. If a name isn't in the transcript, the
field is null.

Respond with the structured fields only.
"""


_FEW_SHOT_EXAMPLES = """Examples of correct judgments. Learn the REASONING; the place names are
throwaway and must never appear in your output unless the citizen said them.

J = {"location_address","address_specific_enough","location_area","location_pincode","pincode_declined","area_same_as_address","issue_clear","issue_clarity_reason"}

1 — area not asked yet, so nothing is settled:
C: Streetlight outside my house flickering a week. / A: Which colony or locality? / C: Rajiv Nagar
{"location_address":"Rajiv Nagar","address_specific_enough":true,"location_area":null,"location_pincode":null,"pincode_declined":false,"area_same_as_address":false,"issue_clear":true,"issue_clarity_reason":"Flickering streetlight for a week is actionable."}

2 — CITIZEN SAYS THE LOCALITY IS THE AREA -> accept at once, never re-ask:
C: Daily 2-3 hr power cuts, worse in rain. / A: Which locality? / C: Shriram Nagar Karegaon Road
A: Which broader area is that in? / C: Area is same as Shriram nagar
{"location_address":"Shriram Nagar Karegaon Road","address_specific_enough":true,"location_area":null,"location_pincode":null,"pincode_declined":false,"area_same_as_address":true,"issue_clear":true,"issue_clarity_reason":"Daily multi-hour power cuts are actionable."}

3 — landmark repeated a SECOND time after area was already asked -> settled:
C: Daily power cuts. / A: Which locality? / C: Shriram nagar / A: Which broader area?
C: Area is same as Shriram nagar / A: Which neighbourhood is Shriram Nagar in?
C: Area is nearest municipal watertank in Shriram nagar
{"location_address":"Shriram Nagar, near the municipal water tank","address_specific_enough":true,"location_area":null,"location_pincode":null,"pincode_declined":false,"area_same_as_address":true,"issue_clear":true,"issue_clarity_reason":"Daily power cuts are actionable."}

4 — FIRST landmark answer to the area question -> one fair re-ask, not settled yet:
C: Short circuit near my house. / A: Which colony? / C: shastri nagar
A: Which broader area? / C: it is near the municipal water tank
{"location_address":"Shastri Nagar, near the municipal water tank","address_specific_enough":true,"location_area":null,"location_pincode":null,"pincode_declined":false,"area_same_as_address":false,"issue_clear":true,"issue_clarity_reason":"A short circuit is actionable."}

5 — "that's all I know" / "no bigger area" / village -> also settled:
C: Sewage overflowing four days. / A: Which locality? / C: Ganesh Colony
A: Which broader area is Ganesh Colony in? / C: that is all I know
{"location_address":"Ganesh Colony","address_specific_enough":true,"location_area":null,"location_pincode":null,"pincode_declined":false,"area_same_as_address":true,"issue_clear":true,"issue_clarity_reason":"Sewage overflowing four days is actionable."}

6 — a genuinely DISTINCT area was named -> record it, nothing asserted:
C: Pothole on Station Road near the grocery shop in Vishrantwadi, pincode 411015, two bikes fell today.
{"location_address":"Station Road, near the grocery shop","address_specific_enough":true,"location_area":"Vishrantwadi","location_pincode":"411015","pincode_declined":false,"area_same_as_address":false,"issue_clear":true,"issue_clarity_reason":"A pothole causing falls is actionable."}

7 — area named in the opening line, locality after (order does not matter; do not re-ask):
C: Drain blocked and overflowing in Yerwada. / A: Which colony or locality? / C: Parvati Housing Society
{"location_address":"Parvati Housing Society","address_specific_enough":true,"location_area":"Yerwada","location_pincode":null,"pincode_declined":false,"area_same_as_address":false,"issue_clear":true,"issue_clarity_reason":"A blocked overflowing drain is actionable."}

8 — answer names nowhere -> genuinely missing, not an assertion:
C: No water supply in my area. / A: Which colony or locality? / C: my area
{"location_address":null,"address_specific_enough":false,"location_area":null,"location_pincode":null,"pincode_declined":false,"area_same_as_address":false,"issue_clear":true,"issue_clarity_reason":"No water supply is actionable though location is unknown."}

9 — issue itself too vague:
C: There is a problem in my area, please fix it.
{"location_address":null,"address_specific_enough":false,"location_area":null,"location_pincode":null,"pincode_declined":false,"area_same_as_address":false,"issue_clear":false,"issue_clarity_reason":"No specific problem described."}

10 — normalization: filler stripped, casing fixed; but "Sector 15" kept whole:
C: no electricity since morning / A: Which colony? / C: shastri nagar / A: Which broader area? / C: gandhi chowk zone
{"location_address":"Shastri Nagar","address_specific_enough":true,"location_area":"Gandhi Chowk","location_pincode":null,"pincode_declined":false,"area_same_as_address":false,"issue_clear":true,"issue_clarity_reason":"No electricity since morning is actionable."}

11 — pincode declined AND area asserted in one conversation:
C: No water three days. / A: Which locality? / C: Hauz Khas, near the market / A: Which broader area?
C: Hauz Khas is the area itself / A: PIN code? / C: No idea, sorry
{"location_address":"Hauz Khas, near the market","address_specific_enough":true,"location_area":null,"location_pincode":"not specified","pincode_declined":true,"area_same_as_address":true,"issue_clear":true,"issue_clarity_reason":"No water for three days is actionable."}

12 — [Context] supplies city+pincode: pincode resolved, city is NOT the area:
[Context: city=Nashik, pincode=422001 given in a form field before this chat.]
C: Stray dogs near the bus stand, children scared. / A: Which colony or locality? / C: Panchavati
{"location_address":"Panchavati","address_specific_enough":true,"location_area":null,"location_pincode":"422001","pincode_declined":false,"area_same_as_address":false,"issue_clear":true,"issue_clarity_reason":"A stray dog menace near a bus stand is actionable."}

---
CURRENT CONVERSATION (judge this only, never repeat example data):
"""


def build_dialogue_user_prompt(transcript_blob: str) -> str:
    return f"{_FEW_SHOT_EXAMPLES}{transcript_blob}\n"
