"""
Chat copy for the conversational intake flow.

The mid-conversation questions (ask_address/ask_area/ask_pincode/
ask_issue_clarification/ask_landmark) are normally authored live by the LLM
(see pipeline/stages.py's run_reply_composer + llm/prompts/compose_reply.py)
so the bot's phrasing is natural and varies turn to turn — the ask_* entries
below are only a fallback used if that LLM call fails, so the conversation
never crashes on a single bad response. Submission confirmations and
rejection reasons stay static/template-based always: they're short, fixed,
and in the rejection case safety-critical (exact emergency numbers must
never be paraphrased by a model), so there's no benefit to generating them
live.

hi/mr entries below are AI-drafted (by this assistant, not a native speaker
review pass) — they cover the intended meaning correctly but, per this
project's own stated multilingual-robustness caveat (see
what_i_am_not_building.md), should get a native-speaker review before any
real deployment. get_template() falls back to English if a language/key
combination is ever missing, so the conversation always still works
end-to-end regardless.
"""
from typing import Optional

TEMPLATES: dict[str, dict[str, str]] = {
    "greeting": {
        "en": "Describe your complaint/Suggestion.",
        "hi": "अपनी शिकायत/सुझाव के बारे में बताएं।",
        "mr": "तुमची तक्रार/सूचना सांगा.",
    },
    "ask_address": {
        "en": "Could you share the colony or locality name where this is happening?",
        "hi": "कृपया बताएं कि यह किस कॉलोनी या इलाके में हो रहा है?",
        "mr": "कृपया सांगा की हे कोणत्या वसाहतीत किंवा परिसरात घडत आहे?",
    },
    "ask_landmark": {
        "en": "Can you give me a nearby landmark, like near the Shivaji building or in front of "
              "the Ravi grocery shop, so I can pinpoint the spot?",
        "hi": "क्या आप कोई नज़दीकी पहचान स्थान (लैंडमार्क) बता सकते हैं, जैसे शिवाजी बिल्डिंग के पास या "
              "रवि किराना दुकान के सामने, ताकि सही जगह पता चल सके?",
        "mr": "तुम्ही जवळची एखादी खूण (लँडमार्क) सांगू शकता का, जसे की शिवाजी बिल्डिंगजवळ किंवा रवी किराणा "
              "दुकानासमोर, म्हणजे नेमकी जागा कळेल?",
    },
    "ask_area": {
        "en": "Which broader area of the city is this in?",
        "hi": "यह शहर के किस बड़े इलाके में है?",
        "mr": "हे शहराच्या कोणत्या मोठ्या भागात आहे?",
    },
    "ask_pincode": {
        "en": "Do you know the PIN code for that area? If not, just say so and we'll continue.",
        "hi": "क्या आपको उस इलाके का पिन कोड पता है? अगर नहीं पता, तो बता दीजिए, हम आगे बढ़ेंगे।",
        "mr": "त्या भागाचा पिन कोड तुम्हाला माहीत आहे का? माहीत नसेल तर तसं सांगा, आपण पुढे जाऊ.",
    },
    "ask_issue_clarification": {
        "en": "Could you describe the issue in a bit more detail — what exactly is happening?",
        "hi": "क्या आप समस्या के बारे में थोड़ा और विस्तार से बता सकते हैं — वास्तव में क्या हो रहा है?",
        "mr": "तुम्ही समस्येबद्दल थोडं अधिक सविस्तर सांगू शकता का — नेमकं काय घडत आहे?",
    },
    "submitted_complaint": {
        "en": "Thanks — your complaint has been submitted and is being reviewed. You can check its "
              "status under \"Track your Complaint\".",
        "hi": "धन्यवाद — आपकी शिकायत दर्ज कर ली गई है और उसकी समीक्षा की जा रही है। आप इसकी स्थिति "
              "\"अपनी शिकायत ट्रैक करें\" में देख सकते हैं।",
        "mr": "धन्यवाद — तुमची तक्रार नोंदवली गेली आहे आणि तिचा आढावा घेतला जात आहे. "
              "\"तुमची तक्रार ट्रॅक करा\" मध्ये तुम्ही तिची स्थिती पाहू शकता.",
    },
    "submitted_suggestion": {
        "en": "Thanks — your suggestion has been submitted and is being reviewed. You can check its "
              "status under \"Track your Suggestion\".",
        "hi": "धन्यवाद — आपका सुझाव दर्ज कर लिया गया है और उसकी समीक्षा की जा रही है। आप इसकी स्थिति "
              "\"अपना सुझाव ट्रैक करें\" में देख सकते हैं।",
        "mr": "धन्यवाद — तुमची सूचना नोंदवली गेली आहे आणि तिचा आढावा घेतला जात आहे. "
              "\"तुमची सूचना ट्रॅक करा\" मध्ये तुम्ही तिची स्थिती पाहू शकता.",
    },
    "rejected_abusive_or_harmful": {
        "en": "Your message contained abusive or harmful language and no describable civic issue, so "
              "it was not registered. Please resubmit describing the actual issue in respectful language.",
        "hi": "आपके संदेश में अपमानजनक या हानिकारक भाषा थी और कोई स्पष्ट नागरिक समस्या नहीं बताई गई, इसलिए "
              "इसे दर्ज नहीं किया गया। कृपया वास्तविक समस्या का सम्मानजनक भाषा में वर्णन करते हुए फिर से भेजें।",
        "mr": "तुमच्या संदेशात अपमानास्पद किंवा हानिकारक भाषा होती आणि कोणतीही स्पष्ट नागरी समस्या नमूद नव्हती, "
              "त्यामुळे तो नोंदवला गेला नाही. कृपया आदरपूर्ण भाषेत खरी समस्या सांगून पुन्हा पाठवा.",
    },
    "rejected_personal_emergency": {
        "en": "This looks like a personal emergency, not a civic infrastructure issue — this portal "
              "cannot dispatch emergency help. Please call 112 (or 108 for ambulance) immediately.",
        "hi": "यह एक व्यक्तिगत आपात स्थिति लगती है, नागरिक बुनियादी ढांचे की समस्या नहीं — यह पोर्टल "
              "आपातकालीन सहायता नहीं भेज सकता। कृपया तुरंत 112 (एम्बुलेंस के लिए 108) पर कॉल करें।",
        "mr": "ही वैयक्तिक आणीबाणीची परिस्थिती वाटते, नागरी पायाभूत सुविधांची समस्या नाही — हे पोर्टल आणीबाणी "
              "मदत पाठवू शकत नाही. कृपया त्वरित 112 (रुग्णवाहिकेसाठी 108) वर कॉल करा.",
    },
    "rejected_spam_or_gibberish": {
        "en": "We couldn't identify a valid complaint or suggestion in your message. Please resubmit "
              "with a clear description of the issue.",
        "hi": "हमें आपके संदेश में कोई मान्य शिकायत या सुझाव नहीं मिला। कृपया समस्या का स्पष्ट विवरण देते हुए "
              "फिर से भेजें।",
        "mr": "तुमच्या संदेशात आम्हाला कोणतीही वैध तक्रार किंवा सूचना आढळली नाही. कृपया समस्येचे स्पष्ट वर्णन "
              "करून पुन्हा पाठवा.",
    },
    "rejected_off_topic": {
        "en": "This message does not appear to relate to a civic/local issue, so it was not registered.",
        "hi": "यह संदेश किसी नागरिक/स्थानीय मुद्दे से संबंधित नहीं लगता, इसलिए इसे दर्ज नहीं किया गया।",
        "mr": "हा संदेश कोणत्याही नागरी/स्थानिक समस्येशी संबंधित दिसत नाही, त्यामुळे तो नोंदवला गेला नाही.",
    },
}


def get_template(key: str, lang: str) -> str:
    """Look up localized copy for `key`, falling back to English if the
    requested language isn't authored yet (or was never a supported one)."""
    entry = TEMPLATES.get(key)
    if not entry:
        raise KeyError(f"Unknown dialogue template key: {key!r}")
    return entry.get(lang) or entry["en"]
