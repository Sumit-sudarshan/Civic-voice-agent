from typing import Literal
from pydantic import BaseModel, Field
from app.models.db_models import UrgencyLevel

class UrgencyResponse(BaseModel):
    urgency: UrgencyLevel = Field(
        ..., description="The calculated urgency level of the complaint."
    )
    reasoning: str = Field(
        ..., description="A short one-sentence explanation of why this urgency level was chosen."
    )

URGENCY_SYSTEM_PROMPT = """You are an expert civic issue triage agent.
Your job is to read a citizen's complaint and assign an urgency level based strictly on the following rubric.

The complaint may be written in Hindi, Marathi, English, or Hinglish (English/Hindi mixed,
Latin script). Understand it regardless of language, but always write "reasoning" in English.

1. critical: Immediate hazard to life, health, or property. Requires dispatch within hours. (e.g., live hanging wire, major pipe burst flooding homes, open deep manhole).
2. high: Severe inconvenience affecting many people, but no immediate life-threat. (e.g., entire block without power, main road blocked by fallen tree, no water supply for a neighborhood).
3. medium: Localized issue causing regular inconvenience. (e.g., pothole, single broken streetlight, uncollected garbage on a street).
4. low: Cosmetic, minor, or long-term issues. (e.g., paint peeling on a public bench, overgrown weeds in a park corner).

Provide your output as a JSON object with keys "urgency" and "reasoning". Provide the reasoning for the input provided only. Do not repeat the examples provided in the prompt.
"""

def build_urgency_user_prompt(text: str) -> str:
    return f"""Below are examples of how to classify complaints:
Input: "A live electricity wire is hanging on the footpath touching the water."
Response: {{"urgency": "critical", "reasoning": "Live wire near water poses an immediate lethal electrocution hazard."}}

Input: "Our entire neighborhood hasn't had water for 2 days."
Response: {{"urgency": "high", "reasoning": "Total lack of water for a neighborhood is a severe public health inconvenience."}}

Input: "There is a pothole on 4th cross street."
Response: {{"urgency": "medium", "reasoning": "A pothole is a localized issue causing inconvenience but no immediate widespread hazard."}}

Input: "The paint on the park swings is fading."
Response: {{"urgency": "low", "reasoning": "Fading paint is purely a cosmetic issue."}}

Input: "{text}"
Response:"""
