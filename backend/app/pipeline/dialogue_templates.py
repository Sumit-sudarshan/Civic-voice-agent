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

Each ask_* key holds a LIST of 5 differently-structured phrasings per
language, not one fixed line. During a real, extended OpenRouter outage
(observed live — see MVP_roadmap.md Phase 4/8/9), every citizen hitting the
fallback path would otherwise see the exact same wording, which reads as
obviously broken/automated rather than as a momentary degradation. get_template
picks a variant deterministically from a caller-supplied seed (typically the
transcript so far) via _stable_variant_index — same seed always yields the
same variant (so the English and localized text composed in one turn always
match), while different conversations naturally land on different phrasings.
This is NOT randomness for its own sake: it's a stable function of real input,
reproducible in tests.

hi/mr entries below are AI-drafted (by this assistant, not a native speaker
review pass) — they cover the intended meaning correctly but, per this
project's own stated multilingual-robustness caveat (see
what_i_am_not_building.md), should get a native-speaker review before any
real deployment. get_template() falls back to English if a language/key
combination is ever missing, so the conversation always still works
end-to-end regardless.
"""
import zlib
from typing import Optional, Union

TEMPLATES: dict[str, dict[str, Union[str, list[str]]]] = {
    "greeting": {
        "en": "Describe your complaint/Suggestion.",
        "hi": "अपनी शिकायत/सुझाव के बारे में बताएं।",
        "mr": "तुमची तक्रार/सूचना सांगा.",
    },
    "ask_address": {
        "en": [
            "Could you share the colony or locality name where this is happening?",
            "What's the name of the colony or locality this issue is in?",
            "To help route this correctly, which colony or locality should I note down?",
            "Which locality or colony is affected — could you tell me its name?",
            "One more detail — what colony or locality is this in?",
        ],
        "hi": [
            "कृपया बताएं कि यह किस कॉलोनी या इलाके में हो रहा है?",
            "यह कॉलोनी या इलाका किस नाम से जाना जाता है?",
            "सही जगह पर भेजने के लिए, कृपया कॉलोनी या इलाके का नाम बताएं।",
            "कौन सी कॉलोनी या इलाका प्रभावित है — कृपया उसका नाम बताएं?",
            "एक और जानकारी — यह किस कॉलोनी या इलाके में है?",
        ],
        "mr": [
            "कृपया सांगा की हे कोणत्या वसाहतीत किंवा परिसरात घडत आहे?",
            "ही वसाहत किंवा परिसर कोणत्या नावाने ओळखला जातो?",
            "योग्य ठिकाणी पाठवण्यासाठी, कृपया वसाहत किंवा परिसराचे नाव सांगा.",
            "कोणती वसाहत किंवा परिसर प्रभावित आहे — कृपया त्याचे नाव सांगा?",
            "आणखी एक तपशील — हे कोणत्या वसाहतीत किंवा परिसरात आहे?",
        ],
    },
    "ask_landmark": {
        "en": [
            "Can you give me a nearby landmark, like near the Shivaji building or in front of "
            "the Ravi grocery shop, so I can pinpoint the spot?",
            "A nearby landmark would help — for example, near a well-known shop, temple, or "
            "building close to the spot.",
            "Is there a recognizable landmark nearby — a shop, school, or building — that would "
            "help pinpoint the exact location?",
            "To narrow it down further, is there a well-known spot nearby, like a market or a "
            "building, I could note?",
            "Could you mention something nearby that's easy to recognize, so the exact spot is clear?",
        ],
        "hi": [
            "क्या आप कोई नज़दीकी पहचान स्थान (लैंडमार्क) बता सकते हैं, जैसे शिवाजी बिल्डिंग के पास या "
            "रवि किराना दुकान के सामने, ताकि सही जगह पता चल सके?",
            "नज़दीकी कोई पहचान स्थान बताना मददगार होगा — जैसे कोई जानी-मानी दुकान, मंदिर या इमारत।",
            "क्या आसपास कोई पहचानने योग्य जगह है — दुकान, स्कूल या इमारत — जो सटीक स्थान बताने में मदद करे?",
            "जगह को और स्पष्ट करने के लिए, क्या पास में कोई जानी-मानी जगह है, जैसे बाज़ार या इमारत, जिसे मैं नोट कर सकूं?",
            "क्या आप आसपास की कोई आसानी से पहचानी जाने वाली चीज़ बता सकते हैं, ताकि सही जगह स्पष्ट हो जाए?",
        ],
        "mr": [
            "तुम्ही जवळची एखादी खूण (लँडमार्क) सांगू शकता का, जसे की शिवाजी बिल्डिंगजवळ किंवा रवी किराणा "
            "दुकानासमोर, म्हणजे नेमकी जागा कळेल?",
            "जवळपासची एखादी ओळखीची जागा सांगितल्यास मदत होईल — जसे की प्रसिद्ध दुकान, मंदिर किंवा इमारत.",
            "आसपास एखादी ओळखता येण्याजोगी जागा आहे का — दुकान, शाळा किंवा इमारत — जी नेमकं ठिकाण सांगण्यास मदत करेल?",
            "ठिकाण अधिक स्पष्ट करण्यासाठी, जवळपास एखादी प्रसिद्ध जागा आहे का, जसे बाजार किंवा इमारत, जी मी नोंदवू शकेन?",
            "जवळपासची सहज ओळखता येईल अशी एखादी गोष्ट सांगू शकता का, म्हणजे नेमकी जागा स्पष्ट होईल?",
        ],
    },
    "ask_area": {
        "en": [
            "Which broader area of the city is this in?",
            "And which larger area of the city does that fall under?",
            "What's the wider neighbourhood or area this belongs to?",
            "Zooming out a bit — which part of the city is this in?",
            "Could you tell me the broader area or neighbourhood as well?",
        ],
        "hi": [
            "यह शहर के किस बड़े इलाके में है?",
            "और यह शहर के किस बड़े इलाके में आता है?",
            "इसका बड़ा इलाका या क्षेत्र कौन सा है?",
            "थोड़ा बड़े स्तर पर देखें तो — यह शहर के किस हिस्से में है?",
            "क्या आप बड़ा इलाका या क्षेत्र भी बता सकते हैं?",
        ],
        "mr": [
            "हे शहराच्या कोणत्या मोठ्या भागात आहे?",
            "आणि हे शहराच्या कोणत्या मोठ्या भागात येते?",
            "याचा मोठा परिसर किंवा भाग कोणता आहे?",
            "थोडं मोठ्या स्तरावर पाहिलं तर — हे शहराच्या कोणत्या भागात आहे?",
            "तुम्ही मोठा परिसर किंवा भागही सांगू शकता का?",
        ],
    },
    "ask_pincode": {
        "en": [
            "Do you know the PIN code for that area? If not, just say so and we'll continue.",
            "If you happen to know the PIN code for that area, that would help — otherwise, no "
            "problem, just let me know.",
            "Do you have the 6-digit PIN code handy? It's fine if you don't.",
            "One last detail — the area's PIN code, if you know it. Feel free to skip it if not.",
            "Would you happen to know the PIN code there? Just say so if you're not sure.",
        ],
        "hi": [
            "क्या आपको उस इलाके का पिन कोड पता है? अगर नहीं पता, तो बता दीजिए, हम आगे बढ़ेंगे।",
            "अगर आपको उस इलाके का पिन कोड पता हो, तो बताइए — नहीं पता तो कोई बात नहीं।",
            "क्या आपके पास 6 अंकों का पिन कोड है? न पता हो तो ठीक है।",
            "आखिरी जानकारी — उस इलाके का पिन कोड, अगर पता हो। नहीं पता तो छोड़ सकते हैं।",
            "क्या आपको वहां का पिन कोड मालूम है? पक्का न हो तो बता दीजिए।",
        ],
        "mr": [
            "त्या भागाचा पिन कोड तुम्हाला माहीत आहे का? माहीत नसेल तर तसं सांगा, आपण पुढे जाऊ.",
            "जर तुम्हाला त्या भागाचा पिन कोड माहीत असेल, तर सांगा — माहीत नसेल तर हरकत नाही.",
            "तुमच्याकडे 6 अंकी पिन कोड आहे का? माहीत नसेल तर ठीक आहे.",
            "शेवटचा तपशील — त्या भागाचा पिन कोड, माहीत असल्यास. माहीत नसेल तर सोडून द्या.",
            "तिथला पिन कोड तुम्हाला माहीत आहे का? खात्री नसेल तर तसं सांगा.",
        ],
    },
    "ask_issue_clarification": {
        "en": [
            "Could you describe the issue in a bit more detail — what exactly is happening?",
            "Can you tell me a little more about what's going on?",
            "I'd like to understand this better — what exactly is the problem?",
            "Could you elaborate a bit on what's happening, so I can note it accurately?",
            "Just to be sure I capture this correctly, could you explain the issue a bit further?",
        ],
        "hi": [
            "क्या आप समस्या के बारे में थोड़ा और विस्तार से बता सकते हैं — वास्तव में क्या हो रहा है?",
            "क्या आप इस बारे में थोड़ा और बता सकते हैं कि क्या हो रहा है?",
            "मैं इसे बेहतर समझना चाहता/चाहती हूं — असल में समस्या क्या है?",
            "क्या आप थोड़ा और विस्तार से बता सकते हैं, ताकि मैं इसे सही तरीके से दर्ज कर सकूं?",
            "बस यह सुनिश्चित करने के लिए कि मैं इसे सही ढंग से समझूं, क्या आप समस्या को थोड़ा और स्पष्ट कर सकते हैं?",
        ],
        "mr": [
            "तुम्ही समस्येबद्दल थोडं अधिक सविस्तर सांगू शकता का — नेमकं काय घडत आहे?",
            "याबद्दल तुम्ही थोडं अधिक सांगू शकता का, नेमकं काय घडत आहे?",
            "मला हे अधिक चांगल्या प्रकारे समजून घ्यायचे आहे — नेमकी समस्या काय आहे?",
            "तुम्ही थोडं अधिक सविस्तर सांगू शकता का, म्हणजे मी हे व्यवस्थित नोंदवू शकेन?",
            "मी हे बरोबर समजून घेतो आहे याची खात्री करण्यासाठी, तुम्ही समस्या थोडी अधिक स्पष्ट करू शकता का?",
        ],
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


def _stable_variant_index(seed: str, count: int) -> int:
    """
    Deterministic, reproducible variant choice — CRC32 rather than Python's
    built-in hash(), since str hashing is randomized per-process by default
    (PYTHONHASHSEED) and would pick a different variant on every restart for
    the exact same seed, breaking both testability and the "same seed always
    yields the same variant" guarantee callers rely on to keep the English
    and localized text of one turn in sync.
    """
    if count <= 1:
        return 0
    return zlib.crc32(seed.encode("utf-8")) % count


def get_template(key: str, lang: str, variation_seed: str = "") -> str:
    """
    Look up localized copy for `key`, falling back to English if the
    requested language isn't authored yet (or was never a supported one).

    `variation_seed` selects which of a multi-variant entry's phrasings is
    used — pass the same seed (e.g. the conversation's transcript so far) for
    both the English and localized calls within one turn so they describe
    the same variant, not two different questions. Single-string entries
    (greeting, submitted_*, rejected_*) ignore it entirely.
    """
    entry = TEMPLATES.get(key)
    if not entry:
        raise KeyError(f"Unknown dialogue template key: {key!r}")
    variants = entry.get(lang) or entry["en"]
    if isinstance(variants, str):
        return variants
    return variants[_stable_variant_index(variation_seed, len(variants))]
