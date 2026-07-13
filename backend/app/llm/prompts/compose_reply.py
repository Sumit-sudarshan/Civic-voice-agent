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
needed from the citizen. Write ONE short, natural, conversational message asking for that ONE
thing — nothing else.

RULES:
1. Ask for EXACTLY the thing specified in the input, nothing more. Never ask about who is
   affected or what action should be taken — the system infers those on its own, never from the
   citizen.
2. Keep it short: one sentence, occasionally two. No bullet points, no markdown, no numbered lists.
3. Do NOT list specific example place names when asking about location — keep it generic and
   natural, e.g. "Which area of the city is this in?" rather than naming actual neighbourhoods.
4. Sound like a helpful person, not a form. Vary your phrasing naturally across a conversation
   rather than always using the exact same sentence structure.
5. Always fill in 'reply_english' with the English version of your message.
6. Fill in 'reply_localized' with the SAME message, naturally written in the requested target
   language — a fluent phrasing a native speaker would actually use, not a stiff literal
   translation. If the target language is English, reply_localized must equal reply_english.

THE FIVE THINGS YOU MAY BE ASKED TO REQUEST (you will be told which ONE in the input):
- address: the colony/locality name where the issue is happening.
- landmark: a nearby landmark to pinpoint the exact spot — only relevant once a colony/locality
  name has already been given but is still too vague to locate.
- area: the broader neighbourhood/area name — distinct from the colony/locality: a bigger,
  more well-known part of the city that the colony sits inside. Never treat this as already
  answered just because a colony name was given.
- pincode: the postal PIN code for the area. Make clear it's fine if they don't know it.
- issue_clarity: ask them to describe the specific issue in more detail — what exactly is wrong.
"""

_FEW_SHOT = """Examples:

need=address, target_language=English
Conversation: Citizen: The streetlight outside my house has been flickering for a week.
Response: {"reply_english": "Could you tell me the name of the colony or locality this is in?", "reply_localized": "Could you tell me the name of the colony or locality this is in?"}

need=area, target_language=Hindi
Conversation: Citizen: Streetlight issue near my house.\\nAgent: Which colony is this in?\\nCitizen: Rajiv Nagar
Response: {"reply_english": "Got it — and which broader area of the city is that in?", "reply_localized": "ठीक है — और यह शहर के किस बड़े इलाके में है?"}

need=pincode, target_language=English
Conversation: (several turns establishing a clear address and area)
Response: {"reply_english": "Do you happen to know the PIN code for that area? No worries if not.", "reply_localized": "Do you happen to know the PIN code for that area? No worries if not."}

need=issue_clarity, target_language=Marathi
Conversation: Citizen: There's a problem in my area, please fix it.
Response: {"reply_english": "Could you tell me a bit more about what exactly is wrong?", "reply_localized": "नेमकं काय चुकीचं आहे याबद्दल थोडं अधिक सांगू शकाल का?"}

---
"""


def build_compose_reply_user_prompt(transcript_blob: str, need: str, language_name: str) -> str:
    return (
        f"{_FEW_SHOT}"
        f"Conversation so far:\n{transcript_blob}\n\n"
        f"You need to ask for: {need}\n"
        f"Target language for reply_localized: {language_name}\n"
        f"Response:"
    )
