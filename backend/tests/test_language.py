from app.pipeline.language import detect_language


def test_detects_hindi():
    assert detect_language("हमारे मोहल्ले में पिछले एक हफ्ते से पानी नहीं आ रहा है।") == "hi"


def test_detects_marathi():
    assert detect_language("आमच्या वॉर्डात रस्त्यावर खूप मोठा खड्डा आहे.") == "mr"


def test_detects_english():
    assert detect_language("There is a huge pothole on MG road.") == "en"


def test_hinglish_falls_back_to_en_not_a_wrong_language():
    """
    Documents a real, deliberate tradeoff: unconstrained langdetect.detect()
    misclassifies this exact sentence as Indonesian ('id') — verified empirically.
    Constraining to {en, hi, mr} (see language.py) turns that wrong guess into a
    reasonable 'en' fallback instead, since Hinglish is Latin-scripted.
    """
    assert detect_language(
        "Bhai humare area mein bahut dino se paani nahi aa raha, please jaldi thik karo."
    ) == "en"


def test_empty_text_defaults_to_en():
    assert detect_language("") == "en"
    assert detect_language("   ") == "en"
