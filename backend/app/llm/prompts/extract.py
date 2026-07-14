from pydantic import BaseModel, Field

class ExtractionResponse(BaseModel):
    location: str = Field(
        ..., description="The full, polished location of the issue, combining the citizen's confirmed "
                          "address/area/pincode with any extra detail from the text."
    )
    issue_summary: str = Field(
        ..., description="A concise 1-2 sentence summary of WHAT is wrong and WHY it matters (cause, "
                          "severity, risk, or scale) — not where it is. Never repeat a landmark or "
                          "place name already captured in the 'location' field."
    )
    affected_parties: str = Field(
        ..., description="Who is specifically impacted. Prefer the exact group named in the text over a "
                          "generic one; only infer when nothing is named, and infer the narrowest group "
                          "the context actually supports."
    )
    ask: str = Field(
        ..., description="What action the citizen wants. Infer from the issue type if not stated."
    )

EXTRACT_SYSTEM_PROMPT = """You are an expert data extraction agent for a civic issue tracking system.
Your job is to read a citizen's complaint or suggestion and extract four structured fields.

RULES:
1. Be concise and factual.
2. Ignore emotional language, rants, or insults — extract only the factual core.
3. You may be given a 'Citizen's Confirmed Location' — this was gathered conversationally and
   confirmed by the citizen (colony/locality name, optional landmark, area, pincode), so treat it
   as ground truth, not a guess to double-check.
4. The citizen's text may be in Hindi, Marathi, English, or Hinglish (English/Hindi mixed, Latin
   script). Understand it regardless of language, but always write all four output fields in English —
   never leave a field in Hindi/Marathi or copy Devanagari script into the output.
5. 'location' and 'issue_summary' must never overlap. Every landmark/place word (e.g. "near the
   school gate", "ATM on Park Street") belongs in 'location' ONLY — do not repeat it inside
   'issue_summary'. Instead, use that space in 'issue_summary' to say what is actually wrong: the
   cause, the danger/severity, or the scale (e.g. "live wire is exposed and could electrocute
   someone" beats "hazard near the school gate" — the reader already knows where it is).

INFERENCE RULES (read carefully — this is the most important part):
- For 'affected_parties': Be specific and correct — this is read by a leader deciding who to worry about, not filler text.
  1. PRIORITY: If the text names or clearly implies a specific group, use THAT group, in its specific form —
     do not smooth it into something more generic. "families with babies" stays "families with babies," not
     "residents." "women walking home at night" stays that, not "pedestrians."
  2. If nothing is named, INFER the NARROWEST group the location/category context actually supports —
     never jump straight to a broad catch-all like "residents," "the public," or "everyone" if a narrower
     group is derivable.
     Examples of good, specific inference:
       * Garbage near a market → "shopkeepers and market visitors"
       * Broken streetlight on a residential street → "residents of that street, especially at night"
       * Hazard near a school → "students, parents, and school staff"
       * Water supply issue in a sector → "households in that sector"
       * Pothole on a main road → "motorists and pedestrians on that road"
  3. CORRECTNESS: never invent a group the context doesn't support — don't say "schoolchildren" unless a
     school or children are actually implicated by the text or location.
  4. Only output "not specified" if there is truly no location, category, or textual context to reason from at all.

- For 'location': produce ONE polished, natural sentence-fragment combining everything that's known.
  * If a "Citizen's Confirmed Location" is given below, weave ALL of its parts (colony/landmark, area,
    pincode — skip any part that is itself "not specified") together with any EXTRA fine-grained detail
    from the text (a specific shop, "near the water tank", "opposite the temple", a house number) into
    one combined description. Do not omit the confirmed area/pincode just because they're structured —
    they are part of the final answer, not something to leave out in favor of only the "extra" bit.
  * If no "Citizen's Confirmed Location" is given at all, extract the location as usual from the text.
    If the text itself is vague and there is nothing to combine, output "not specified".

- For 'ask': Infer the expected civic action from the type of issue if not explicitly stated.
  Examples: broken pipe → "Fix the pipe"; garbage → "Resume garbage collection";
  pothole → "Fill the pothole"; no water → "Restore water supply".
  Only output "not specified" if the issue is too ambiguous to infer any action.
"""

_FEW_SHOT_EXAMPLES = """Below are examples of correct extractions. Study them, then extract the CURRENT INPUT at the end.

EXAMPLE 1:
Input: "The main water pipe burst in front of the school and the road is flooded."
Answer: {"location": "In front of the school", "issue_summary": "Burst water pipe has flooded the road.", "affected_parties": "School children, commuters, and nearby residents", "ask": "Fix the pipe and clear the floodwater."}

EXAMPLE 2:
Input: "Plant more trees along MG Road."
Answer: {"location": "MG Road", "issue_summary": "Request to plant more trees along MG Road.", "affected_parties": "Pedestrians and residents along MG Road", "ask": "Plant trees along MG Road."}

EXAMPLE 3:
Input: "I am sick and tired of this corrupt municipality! There's a massive pothole outside building 42 on 5th avenue and my car suspension is broken! FIX IT NOW!"
Answer: {"location": "Outside building 42, 5th avenue", "issue_summary": "Large pothole causing vehicle damage.", "affected_parties": "Motorists and residents of 5th avenue", "ask": "Fill the pothole."}

EXAMPLE 4:
Input: "The streetlights in our lane are broken."
Answer: {"location": "not specified", "issue_summary": "Broken streetlights in a residential lane.", "affected_parties": "Residents of the lane, especially those traveling at night", "ask": "Repair or replace the broken streetlights."}

EXAMPLE 5:
Input: "Garbage hasn't been collected in Sector 4 for over a week."
Answer: {"location": "Sector 4", "issue_summary": "Garbage collection has been absent for over a week.", "affected_parties": "All residents of Sector 4", "ask": "Resume regular garbage collection in Sector 4."}

EXAMPLE 6 (Citizen's Confirmed Location is given — combine ALL its parts with any extra text detail):
Citizen's Confirmed Location: "Ambedkar Nagar, near the water tank; area: Cotton Green; pincode: 400033"
Input: "There's a huge pothole right in front of Patil's shop, someone's going to get hurt."
Answer: {"location": "Ambedkar Nagar, near the water tank, in front of Patil's shop, Cotton Green, 400033", "issue_summary": "Large pothole poses an injury risk.", "affected_parties": "Motorists and pedestrians near the water tank", "ask": "Fill the pothole."}

EXAMPLE 7 (Citizen's Confirmed Location given, text has no extra detail beyond it — still combine the confirmed parts):
Citizen's Confirmed Location: "Rohini; area: Rohini; pincode: not specified"
Input: "We haven't had water for three days now, this is ridiculous."
Answer: {"location": "Rohini", "issue_summary": "No water supply for three days.", "affected_parties": "Households in the area", "ask": "Restore water supply."}

EXAMPLE 8 (text names a specific group — keep it specific, do NOT generalize to "residents"):
Input: "This is unacceptable, the water tanker for Adyar hasn't shown up in 4 days and we have babies at home, what exactly are we supposed to do?!"
Answer: {"location": "Adyar", "issue_summary": "Water tanker has not arrived for 4 days.", "affected_parties": "Families with babies in Adyar", "ask": "Restore water supply to Adyar."}

EXAMPLE 9 (landmark goes in 'location' ONLY — issue_summary explains the danger/cause instead of repeating it):
Input: "There's a live wire hanging loose near the school gate on Anna Nagar main road, someone is going to get electrocuted."
Answer: {"location": "Anna Nagar main road, near the school gate", "issue_summary": "A live wire is exposed and hanging loose, posing an electrocution risk.", "affected_parties": "Students, parents, and school staff", "ask": "Immediately de-energize and repair the exposed wire."}

---
CURRENT INPUT (extract this only, do not repeat example data):
"""

def build_extract_user_prompt(text: str, known_location: str = None) -> str:
    context_line = f'Citizen\'s Confirmed Location: "{known_location}"\n' if known_location else ""
    return f'{_FEW_SHOT_EXAMPLES}{context_line}Input: "{text}"\n'
