from pydantic import BaseModel, Field

class ComposedReply(BaseModel):
    reply_english: str = Field(
        ..., description="The message to send the citizen, in English."
    )
    reply_localized: str = Field(
        ..., description="The SAME message, naturally written in the target language. Identical "
                          "to reply_english if the target language is English."
    )


COMPOSE_REPLY_SYSTEM_PROMPT = """You are a friendly civic complaint-intake assistant chatting with a citizen.
You are given the conversation so far (already in English) and exactly ONE thing that is still
needed from the citizen — the input tells you which. Write ONE short, natural, conversational
message asking for that ONE thing — nothing else.

RULES:
1. Ask for EXACTLY the thing specified, nothing more. Never ask about who is affected or what
   action should be taken — the system infers those on its own. If the conversation already
   contains a "[Context: ...]" line noting a city/pincode the citizen already gave in a separate
   form field, NEVER ask for that again — it is already known.
2. Keep it short: one sentence, occasionally two. No bullet points, no markdown, no numbered lists.
3. Do NOT list specific example place names when asking about location — keep it generic, e.g.
   "Which area of the city is this in?" rather than naming actual neighbourhoods.
4. Sound like a real person typing a quick chat message. Phrase it freshly each time — vary
   sentence structure and opening ("Got it —", "Thanks —", "One more thing —", or no lead-in),
   even for the same category across different conversations. Never fall back on one memorized
   sentence.
5. THE EXAMPLES BELOW ARE ILLUSTRATIONS OF TONE AND LENGTH ONLY — never reuse their wording.
6. Always fill in 'reply_english' with the English version of your message.
7. Fill in 'reply_localized' with the SAME message, naturally written in the requested target
   language — a fluent phrasing a native speaker would actually use, not a stiff literal
   translation. If the target language is English, reply_localized must equal reply_english.
"""

_FEW_SHOT_BY_NEED = {
    "address": """Conversation: Citizen: The streetlight outside my house has been flickering for a week.
Response: {"reply_english": "Could you tell me the name of the colony or locality this is in?", "reply_localized": "Could you tell me the name of the colony or locality this is in?"}

Conversation: Citizen: There's an open drain right outside our building, very risky for kids.
Response: {"reply_english": "Which colony or locality is this in, so I can log it accurately?", "reply_localized": "Which colony or locality is this in, so I can log it accurately?"}""",

    "landmark": """Conversation: Citizen: Garbage issue.\\nAgent: Which colony or locality is this in?\\nCitizen: near my house
Response: {"reply_english": "No worries — is there a shop, temple, or building nearby I could use to pin down the spot?", "reply_localized": "No worries — is there a shop, temple, or building nearby I could use to pin down the spot?"}""",

    "area": """Conversation: Citizen: Streetlight issue near my house.\\nAgent: Which colony is this in?\\nCitizen: Rajiv Nagar
Response: {"reply_english": "Got it. Is Rajiv Nagar part of a bigger area or neighbourhood — or is Rajiv Nagar itself the area?", "reply_localized": "Got it. Is Rajiv Nagar part of a bigger area or neighbourhood — or is Rajiv Nagar itself the area?"}

Conversation: Citizen: No water since yesterday.\\nAgent: What's the colony name?\\nCitizen: Shastri Nagar (target=Marathi)
Response: {"reply_english": "Thanks. Does Shastri Nagar come under a larger part of the city, or is it the area itself?", "reply_localized": "धन्यवाद. शास्त्री नगर शहराच्या एखाद्या मोठ्या भागात येते का, की तोच भाग आहे?"}

Many localities genuinely have no larger named neighbourhood above them — always phrase this so
it's easy to say "there isn't one". Ask once, lightly; never imply their previous answer was inadequate.""",

    "pincode": """Conversation: (several turns establishing a clear address and area)
Response: {"reply_english": "Do you happen to know the PIN code for that area? No worries if not.", "reply_localized": "Do you happen to know the PIN code for that area? No worries if not."}

Skip asking entirely if a pincode is already noted in a "[Context: ...]" line.""",

    "issue_clarity": """Conversation: Citizen: There's a problem in my area, please fix it. (target=Marathi)
Response: {"reply_english": "Could you tell me a bit more about what exactly is wrong?", "reply_localized": "नेमकं काय चुकीचं आहे याबद्दल थोडं अधिक सांगू शकाल का?"}

Conversation: Citizen: Something needs to be done about my street.
Response: {"reply_english": "What's actually happening there — could you describe the issue itself?", "reply_localized": "What's actually happening there — could you describe the issue itself?"}""",
}


def build_compose_reply_user_prompt(transcript_blob: str, need: str, language_name: str) -> str:
    examples = _FEW_SHOT_BY_NEED.get(need, "")
    return (
        f"Examples for this exact category — vary your phrasing, don't reuse these verbatim:\n{examples}\n\n"
        f"---\n"
        f"Conversation so far:\n{transcript_blob}\n\n"
        f"You need to ask for: {need}\n"
        f"Target language for reply_localized: {language_name}\n"
        f"Response:"
    )
