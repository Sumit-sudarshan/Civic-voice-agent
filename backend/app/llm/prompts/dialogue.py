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
        None, description="The broader area/neighbourhood name — a bigger, more well-known part of the "
                           "city that the colony/locality sits inside (e.g. colony 'Rajiv Nagar' might "
                           "sit inside area 'Bandra'). This must be a genuinely different, named place "
                           "from location_address, never the same text repeated, and never a landmark, "
                           "shop, tank, or other descriptive detail. None if a real, distinct area name "
                           "has not been given yet — do NOT fill this in just because SOME location "
                           "detail exists; a vague answer to 'which area?' (like a landmark description) "
                           "means this is still None."
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


DIALOGUE_SYSTEM_PROMPT = """You are the diagnostic component of a civic-complaint intake conversation.
You are given the transcript of a conversation between a citizen and an assistant so far. Your ONLY
job is to judge what is currently known and what is still missing — you do not write questions or
any citizen-facing text.

The transcript is always in English (any Hindi/Marathi/Hinglish input has already been translated
before you see it). Read the whole transcript, not just the latest line — earlier citizen turns may
already contain the address, area, pincode, or issue detail, and a short reply like "400033" or
"near the temple" only makes sense in light of the Agent question immediately before it.

A transcript may open with a "[Context: ...]" line — this is NOT something the citizen said in
the chat. It is a city and/or pincode the citizen already typed into a separate form field before
this conversation started. If a pincode is given there, treat location_pincode as already resolved
to that value. The city named there is NOT the same thing as location_area: area is a smaller,
specifically-named neighbourhood inside that city (e.g. city "Pune" might contain area "Kothrud"),
never the city itself — do not fill location_area with the city name from this context line.

THE MOST IMPORTANT RULE, READ THIS CAREFULLY: location_address and location_area are TWO DIFFERENT
THINGS and must never be filled with the same value or with something that isn't genuinely that
field. A colony/locality name (location_address) is a small, specific place. An area (location_area)
is the bigger, more well-known part of the city it sits inside — a different, named place, not a
landmark or descriptive phrase. If the citizen's answer to an area question is actually a landmark,
shop name, or vague description (not a real area name), location_area is STILL None — do not accept
it as an area just because the citizen said something. When in doubt about whether a field has
genuinely been filled, leave it None/False rather than guessing — a missing field just means one more
short question gets asked, which is always safer than inventing information that was never given.

Never invent a value that was not actually stated in the transcript. Respond with the structured
fields only.

NORMALIZING location_area: the same real area can be said in slightly different ways by different
citizens (e.g. "Cotton Green", "Cotton Green Area", "cotton green zone", "Koramangala locality") —
these all refer to the exact same place and MUST be written back the same way every time, so two
citizens reporting the same area are stored as identical text, not near-miss variants. To do this:
strip generic suffix/filler words like "Area", "Zone", "Locality", "Region", "Part", "Sector" (unless
that word is genuinely part of the area's own proper name), fix casing to Title Case, and trim extra
whitespace. Always output just the clean proper-noun place name itself, e.g. "Cotton Green", not
"Cotton Green Area" or "cotton green". Do this same normalization for location_address too.
"""


_FEW_SHOT_EXAMPLES = """Below are examples of correct judgments. Study them, then judge the CURRENT CONVERSATION at the end.

EXAMPLE 1 — only a colony name given, nothing else yet:
Conversation:
Citizen: The streetlight outside my house has been flickering for a week.
Agent: Could you share the colony or locality name where this is happening?
Citizen: Rajiv Nagar
Judgment: {"location_address": "Rajiv Nagar", "address_specific_enough": true, "location_area": null, "location_pincode": null, "pincode_declined": false, "issue_clear": true, "issue_clarity_reason": "Flickering streetlight for a week is a specific, actionable issue."}

EXAMPLE 2 — citizen gives a landmark instead of a real area name when asked for area (area is STILL None):
Conversation:
Citizen: There is a short circuit near my house.
Agent: Could you share the colony or locality name where this is happening?
Citizen: shriram nagar
Agent: Which broader area of the city is this in?
Citizen: it is near the municipal water tank
Judgment: {"location_address": "Shriram Nagar, near the municipal water tank", "address_specific_enough": true, "location_area": null, "location_pincode": null, "pincode_declined": false, "issue_clear": true, "issue_clarity_reason": "Short circuit is a specific, actionable issue."}
(Note: "near the municipal water tank" is landmark detail, folded into location_address — it is NOT a real area name, so location_area stays null even though an area question was already asked.)

EXAMPLE 3 — colony AND a genuinely distinct area both given:
Conversation:
Citizen: Massive pothole on MG Road near Ravi's grocery shop in Cotton Green, pincode 400021, two bikes have fallen today.
Judgment: {"location_address": "MG Road, near Ravi's grocery shop", "address_specific_enough": true, "location_area": "Cotton Green", "location_pincode": "400021", "pincode_declined": false, "issue_clear": true, "issue_clarity_reason": "Pothole causing accidents is specific and actionable."}

EXAMPLE 4 — citizen declines to give a pincode after being asked:
Conversation:
Citizen: No water supply in our building for three days.
Agent: Could you share the colony or locality name where this is happening?
Citizen: Hauz Khas, near the market
Agent: Which broader area of the city is this in?
Citizen: Hauz Khas is the area itself
Agent: Do you know the PIN code for that area?
Citizen: No idea, sorry
Judgment: {"location_address": "near the market", "address_specific_enough": true, "location_area": "Hauz Khas", "location_pincode": "not specified", "pincode_declined": true, "issue_clear": true, "issue_clarity_reason": "No water supply for three days is specific and actionable."}

EXAMPLE 5 — issue itself is too vague, nothing else known yet:
Conversation:
Citizen: There's a problem in my area, please fix it.
Judgment: {"location_address": null, "address_specific_enough": false, "location_area": null, "location_pincode": null, "pincode_declined": false, "issue_clear": false, "issue_clarity_reason": "No specific problem described — could be anything."}

EXAMPLE 7 — colony answer is too vague ("my area"/"nearby only") — address_specific_enough must be false so a landmark gets asked next, NOT accepted as-is:
Conversation:
Citizen: There's no water supply in my area.
Agent: Could you share the colony or locality name where this is happening?
Citizen: my area
Judgment: {"location_address": null, "address_specific_enough": false, "location_area": null, "location_pincode": null, "pincode_declined": false, "issue_clear": true, "issue_clarity_reason": "No water supply is a specific, actionable issue even though location is still vague."}
(Note: "my area"/"here"/"nearby" is not an actual colony/locality name — it gives no one a real place to look, so location_address stays null and address_specific_enough stays false, which prompts a landmark question next rather than giving up.)

EXAMPLE 6 — pincode has simply never come up yet (must be null, NOT "not specified"):
Conversation:
Citizen: Garbage hasn't been collected in two weeks.
Agent: Could you share the colony or locality name where this is happening?
Citizen: Indiranagar
Judgment: {"location_address": "Indiranagar", "address_specific_enough": true, "location_area": null, "location_pincode": null, "pincode_declined": false, "issue_clear": true, "issue_clarity_reason": "Garbage not collected for two weeks is specific and actionable."}

EXAMPLE 8 — area given with an "Area" suffix, must be stripped to the clean place name:
Conversation:
Citizen: Streetlight pole fell over near my building.
Agent: Could you share the colony or locality name where this is happening?
Citizen: Rajiv Nagar
Agent: Which broader area of the city is this in?
Citizen: Cotton Green Area
Judgment: {"location_address": "Rajiv Nagar", "address_specific_enough": true, "location_area": "Cotton Green", "location_pincode": null, "pincode_declined": false, "issue_clear": true, "issue_clarity_reason": "A fallen streetlight pole is specific and actionable."}
(Note: "Cotton Green Area" is normalized to "Cotton Green" — the word "Area" is generic filler, not part of the place's real name, so it is stripped.)

EXAMPLE 9 — area given in lowercase with a "zone" suffix, must be normalized to Title Case with the suffix stripped:
Conversation:
Citizen: no electricity since morning in my street
Agent: Could you share the colony or locality name where this is happening?
Citizen: shastri nagar
Agent: Which broader area of the city is this in?
Citizen: bandra east zone
Judgment: {"location_address": "Shastri Nagar", "address_specific_enough": true, "location_area": "Bandra East", "location_pincode": null, "pincode_declined": false, "issue_clear": true, "issue_clarity_reason": "No electricity since morning is specific and actionable."}
(Note: "bandra east zone" normalizes to "Bandra East" — casing fixed to Title Case, "zone" filler stripped.)

EXAMPLE 10 — area given with a "locality" suffix and extra whitespace, must be cleaned to the bare place name:
Conversation:
Citizen: Open manhole outside the school gate, very dangerous.
Agent: Could you share the colony or locality name where this is happening?
Citizen: Near the school
Agent: Which broader area of the city is this in?
Citizen:   Koramangala   Locality
Judgment: {"location_address": "Near the school", "address_specific_enough": true, "location_area": "Koramangala", "location_pincode": null, "pincode_declined": false, "issue_clear": true, "issue_clarity_reason": "An open manhole is an immediate safety hazard and is specific and actionable."}
(Note: extra spaces trimmed and "Locality" filler stripped — "Koramangala" is the clean, reusable form.)

EXAMPLE 11 — area name IS genuinely just given plainly already, so it is kept as-is (no filler to strip, no suffix word is part of a real compound area name here):
Conversation:
Citizen: Garbage piling up near the market for a week now.
Agent: Could you share the colony or locality name where this is happening?
Citizen: near the market itself
Agent: Which broader area of the city is this in?
Citizen: Whitefield
Judgment: {"location_address": "near the market", "address_specific_enough": true, "location_area": "Whitefield", "location_pincode": null, "pincode_declined": false, "issue_clear": true, "issue_clarity_reason": "Garbage piling up for a week is specific and actionable."}
(Note: "Whitefield" already has no filler word to strip and correct casing, so it is used unchanged — normalization means cleaning up filler/casing when present, not altering a name that is already clean.)

EXAMPLE 12 — do NOT strip a word that is genuinely part of the area's real proper name just because it resembles a filler word:
Conversation:
Citizen: Water tank near my house is leaking badly.
Agent: Could you share the colony or locality name where this is happening?
Citizen: Vrindavan Colony
Agent: Which broader area of the city is this in?
Citizen: Sector 15
Judgment: {"location_address": "Vrindavan Colony", "address_specific_enough": true, "location_area": "Sector 15", "location_pincode": null, "pincode_declined": false, "issue_clear": true, "issue_clarity_reason": "A leaking water tank is specific and actionable."}
(Note: "Sector 15" is kept whole — "Sector" here is genuinely part of this area's actual name, not generic filler, since the number makes it a specific named place, not a description.)

---
CURRENT CONVERSATION (judge this only, do not repeat example data):
"""


def build_dialogue_user_prompt(transcript_blob: str) -> str:
    return f"{_FEW_SHOT_EXAMPLES}{transcript_blob}\n"
