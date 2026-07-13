"""
Indic -> English translation for the conversational intake flow, using
AI4Bharat's IndicTrans2 (ai4bharat/indictrans2-indic-en-dist-200M) — MIT
licensed, purpose-built for the 22 scheduled languages of India (including
Hindi and Marathi), with a distilled 200M-parameter checkpoint small enough
to run on CPU alongside the Ollama-served LLM.

Only this ONE direction (Indic -> English) is a runtime dependency — see the
rationale in dialogue_templates.py: bot-authored copy is static/pre-translated,
so English -> Indic is never needed live.

The model is lazily loaded and cached at module level on first use, so a
conversation that never contains Hindi/Marathi input never pays the load
cost at all.

Uses the vendored pure-Python `IndicProcessor` (see pipeline/_indic_processor.py)
for pre/post-processing instead of the published `IndicTransToolkit` PyPI
package — that package only ships a Cython-compiled build requiring a C++
toolchain unavailable in this environment; the vendored module is the
identical (MIT-licensed) logic without that build dependency.

IMPORTANT — one-time manual setup required: this model repo is "gated" on
Hugging Face (access is auto-approved, but still requires an authenticated
account). Without it, `_load()` fails and every call falls back to
returning the original text unchanged — the chat still works end-to-end,
it just won't translate Hindi/Marathi input. To enable real translation:
  1. Create a free account at https://huggingface.co (if you don't have one).
  2. Visit https://huggingface.co/ai4bharat/indictrans2-indic-en-dist-200M
     and click "Agree and access repository" (instant, automatic approval).
  3. Create an access token: https://huggingface.co/settings/tokens
  4. Log in from this machine: `huggingface-cli login` (paste the token),
     or set the `HF_TOKEN` environment variable.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_MODEL_NAME = "ai4bharat/indictrans2-indic-en-dist-200M"
_LANG_CODE_MAP = {"hi": "hin_Deva", "mr": "mar_Deva"}
_TARGET_LANG_CODE = "eng_Latn"

_state = {"loaded": False, "tokenizer": None, "model": None, "processor": None}


def _load():
    """Loads the tokenizer/model/processor once, caching them at module
    level. Returns True on success, False on any failure (missing
    dependency, download failure, etc.) — callers treat False as
    "translation unavailable, pass text through unchanged"."""
    if _state["loaded"]:
        return _state["model"] is not None

    _state["loaded"] = True
    try:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        from app.pipeline._indic_processor import IndicProcessor
        from app.config import settings

        hf_token = settings.HF_TOKEN or None

        logger.info(f"Loading translation model {_MODEL_NAME} (first Hindi/Marathi message this run)...")
        tokenizer = AutoTokenizer.from_pretrained(_MODEL_NAME, trust_remote_code=True, token=hf_token)
        model = AutoModelForSeq2SeqLM.from_pretrained(_MODEL_NAME, trust_remote_code=True, token=hf_token)
        model.eval()

        _state["tokenizer"] = tokenizer
        _state["model"] = model
        _state["processor"] = IndicProcessor(inference=True)
        _state["torch"] = torch
        logger.info("Translation model loaded successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to load translation model {_MODEL_NAME}: {e}")
        _state["model"] = None
        return False


def translate_to_english(text: str, source_lang: str) -> str:
    """
    source_lang is "hi" or "mr". Best-effort: must never raise — on any
    failure (model unavailable, inference error), return the original text
    unchanged rather than blocking the conversation. Downstream LLM prompts
    already have Hinglish/mixed-script handling as a safety net, so an
    untranslated Devanagari string is strictly better passed through than a
    crashed turn.
    """
    if not text or not text.strip():
        return text

    src_code = _LANG_CODE_MAP.get(source_lang)
    if not src_code:
        return text

    if not _load():
        return text

    try:
        torch = _state["torch"]
        tokenizer = _state["tokenizer"]
        model = _state["model"]
        ip = _state["processor"]

        batch = ip.preprocess_batch([text], src_lang=src_code, tgt_lang=_TARGET_LANG_CODE)
        inputs = tokenizer(batch, truncation=True, padding="longest", return_tensors="pt")

        with torch.no_grad():
            generated_tokens = model.generate(
                **inputs, use_cache=True, min_length=0, max_length=256, num_beams=5,
            )

        decoded = tokenizer.batch_decode(
            generated_tokens, skip_special_tokens=True, clean_up_tokenization_spaces=True,
        )
        translated = ip.postprocess_batch(decoded, lang=_TARGET_LANG_CODE)
        return translated[0] if translated else text
    except Exception as e:
        logger.error(f"Translation inference failed, passing text through unchanged: {e}")
        return text
