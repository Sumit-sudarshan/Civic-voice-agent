"""
Vendored pure-Python `IndicProcessor` from AI4Bharat/VarunGumma's
IndicTransToolkit (https://github.com/VarunGumma/IndicTransToolkit),
MIT licensed (Copyright (c) Varun Gumma).

Why vendored instead of `pip install IndicTransToolkit`: the published
PyPI package only ships a Cython-compiled build of this same class, which
requires a C++ toolchain (Microsoft Visual C++ Build Tools) to compile from
source on Windows — not available in this environment, and too heavy a
system-level install to require for a demo project. This file is the
pre-Cython pure-Python implementation of the identical class (same
preprocess_batch/postprocess_batch behavior, same FLORES language-code
handling), taken from the toolkit's git history before the Cython rewrite
was added, at commit 0c607654. Only dependencies are `regex`/`re`, `tqdm`,
`sacremoses`, and `indic-nlp-library` — all pure Python, no compiler needed.

Do not hand-edit the logic below; if the upstream fixes a bug here, re-vendor
from the same source rather than patching independently.
"""
import re
from tqdm import tqdm
from queue import Queue
from typing import List, Tuple, Union

from indicnlp.tokenize import indic_tokenize, indic_detokenize
from indicnlp.normalize.indic_normalize import IndicNormalizerFactory
from sacremoses import MosesPunctNormalizer, MosesTokenizer, MosesDetokenizer
from indicnlp.transliterate.unicode_transliterate import UnicodeIndicTransliterator


class IndicProcessor:
    def __init__(self, inference=True):
        self.inference = inference

        self._flores_codes = {
            "asm_Beng": "as",
            "awa_Deva": "hi",
            "ben_Beng": "bn",
            "bho_Deva": "hi",
            "brx_Deva": "hi",
            "doi_Deva": "hi",
            "eng_Latn": "en",
            "gom_Deva": "kK",
            "gon_Deva": "hi",
            "guj_Gujr": "gu",
            "hin_Deva": "hi",
            "hne_Deva": "hi",
            "kan_Knda": "kn",
            "kas_Arab": "ur",
            "kas_Deva": "hi",
            "kha_Latn": "en",
            "lus_Latn": "en",
            "mag_Deva": "hi",
            "mai_Deva": "hi",
            "mal_Mlym": "ml",
            "mar_Deva": "mr",
            "mni_Beng": "bn",
            "mni_Mtei": "hi",
            "npi_Deva": "ne",
            "ory_Orya": "or",
            "pan_Guru": "pa",
            "san_Deva": "hi",
            "sat_Olck": "or",
            "snd_Arab": "ur",
            "snd_Deva": "hi",
            "tam_Taml": "ta",
            "tel_Telu": "te",
            "urd_Arab": "ur",
            "unr_Deva": "hi",
        }

        self._indic_num_map = {
            "০": "0", "0": "0", "૦": "0", "೦": "0", "०": "0",
            "٠": "0", "꯰": "0", "୦": "0", "੦": "0", "᱐": "0", "۰": "0",
            "১": "1", "1": "1", "૧": "1", "१": "1", "೧": "1",
            "۱": "1", "꯱": "1", "୧": "1", "੧": "1", "᱑": "1", "౧": "1",
            "২": "2", "2": "2", "૨": "2", "२": "2", "೨": "2",
            "۲": "2", "꯲": "2", "୨": "2", "੨": "2", "᱒": "2", "౨": "2",
            "৩": "3", "3": "3", "૩": "3", "३": "3", "೩": "3",
            "۳": "3", "꯳": "3", "୩": "3", "੩": "3", "᱓": "3", "౩": "3",
            "৪": "4", "4": "4", "૪": "4", "४": "4", "೪": "4",
            "۴": "4", "꯴": "4", "୪": "4", "੪": "4", "᱔": "4", "౪": "4",
            "৫": "5", "5": "5", "૫": "5", "५": "5", "೫": "5",
            "۵": "5", "꯵": "5", "୫": "5", "੫": "5", "᱕": "5", "౫": "5",
            "৬": "6", "6": "6", "૬": "6", "६": "6", "೬": "6",
            "۶": "6", "꯶": "6", "୬": "6", "੬": "6", "᱖": "6", "౬": "6",
            "৭": "7", "7": "7", "૭": "7", "७": "7", "೭": "7",
            "۷": "7", "꯷": "7", "୭": "7", "੭": "7", "᱗": "7", "౭": "7",
            "৮": "8", "8": "8", "૮": "8", "८": "8", "೮": "8",
            "۸": "8", "꯸": "8", "୮": "8", "੮": "8", "᱘": "8", "౮": "8",
            "৯": "9", "9": "9", "૯": "9", "९": "9", "೯": "9",
            "۹": "9", "꯹": "9", "୯": "9", "੯": "9", "᱙": "9", "౯": "9",
        }

        self._placeholder_entity_maps = Queue()

        self._en_tok = MosesTokenizer(lang="en")
        self._en_normalizer = MosesPunctNormalizer()
        self._en_detok = MosesDetokenizer(lang="en")
        self._xliterator = UnicodeIndicTransliterator()

        self._multispace_regex = re.compile("[ ]{2,}")
        self._digit_space_percent = re.compile(r"(\d) %")
        self._double_quot_punc = re.compile(r"\"([,\.]+)")
        self._digit_nbsp_digit = re.compile(r"(\d) (\d)")
        self._end_bracket_space_punc_regex = re.compile(r"\) ([\.!:?;,])")

        self._URL_PATTERN = r"\b(?<![\w/.])(?:(?:https?|ftp)://)?(?:(?:[\w-]+\.)+(?!\.))(?:[\w/\-?#&=%.]+)+(?!\.\w+)\b"
        self._NUMERAL_PATTERN = r"(~?\d+\.?\d*\s?%?\s?-?\s?~?\d+\.?\d*\s?%|~?\d+%|\d+[-\/.,:']\d+[-\/.,:'+]\d+(?:\.\d+)?|\d+[-\/.:'+]\d+(?:\.\d+)?)"
        self._EMAIL_PATTERN = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}"
        self._OTHER_PATTERN = r"[A-Za-z0-9]*[#|@]\w+"

    def get_batches(self, sentences: List[str], batch_size=8):
        for i in tqdm(range(0, len(sentences), batch_size)):
            yield sentences[i : i + batch_size]

    def _punc_norm(self, text) -> str:
        text = (
            text.replace("\r", "")
            .replace("(", " (")
            .replace(")", ") ")
            .replace("( ", "(")
            .replace(" )", ")")
            .replace(" :", ":")
            .replace(" ;", ";")
            .replace("`", "'")
            .replace("„", '"')
            .replace("“", '"')
            .replace("”", '"')
            .replace("–", "-")
            .replace("—", " - ")
            .replace("´", "'")
            .replace("‘", "'")
            .replace("‚", "'")
            .replace("’", "'")
            .replace("''", '"')
            .replace("´´", '"')
            .replace("…", "...")
            .replace(" « ", ' "')
            .replace("« ", '"')
            .replace("«", '"')
            .replace(" » ", '" ')
            .replace(" »", '"')
            .replace("»", '"')
            .replace(" %", "%")
            .replace("nº ", "nº ")
            .replace(" :", ":")
            .replace(" ºC", " ºC")
            .replace(" cm", " cm")
            .replace(" ?", "?")
            .replace(" !", "!")
            .replace(" ;", ";")
            .replace(", ", ", ")
        )

        text = self._multispace_regex.sub(" ", text)
        text = self._end_bracket_space_punc_regex.sub(r")\1", text)
        text = self._digit_space_percent.sub(r"\1%", text)
        text = self._double_quot_punc.sub(r'\1"', text)
        text = self._digit_nbsp_digit.sub(r"\1.\2", text)
        return text.strip()

    def _normalize_indic_numerals(self, line: str) -> str:
        return "".join([self._indic_num_map.get(c, c) for c in line])

    def _wrap_with_placeholders(self, text: str, patterns: list) -> str:
        serial_no = 1
        placeholder_entity_map = {}

        indic_failure_cases = [
            "آی ڈی ", "ꯑꯥꯏꯗꯤ", "आईडी", "आई . डी . ", "आई . डी .", "आई. डी. ", "आई. डी.",
            "आय. डी. ", "आय. डी.", "आय . डी . ", "आय . डी .", "ऐटि", "آئی ڈی ", "ᱟᱭᱰᱤ ᱾",
            "आयडी", "ऐडि", "आइडि", "ᱟᱭᱰᱤ",
        ]

        for pattern in patterns:
            matches = set(re.findall(pattern, text))

            for match in matches:
                if pattern == self._URL_PATTERN:
                    if len(match.replace(".", "")) < 4:
                        continue
                if pattern == self._NUMERAL_PATTERN:
                    if (
                        len(match.replace(" ", "").replace(".", "").replace(":", ""))
                        < 4
                    ):
                        continue

                base_placeholder = f"<ID{serial_no}>"

                placeholder_entity_map[f"<ID{serial_no}]"] = match
                placeholder_entity_map[f"< ID{serial_no} ]"] = match
                placeholder_entity_map[f"<ID{serial_no}>"] = match
                placeholder_entity_map[f"< ID{serial_no} >"] = match
                placeholder_entity_map[f"[ID{serial_no}]"] = match
                placeholder_entity_map[f"[ID {serial_no}]"] = match
                placeholder_entity_map[f"[ ID{serial_no} ]"] = match

                for i in indic_failure_cases:
                    placeholder_entity_map[f"<{i}{serial_no}>"] = match
                    placeholder_entity_map[f"< {i}{serial_no} >"] = match
                    placeholder_entity_map[f"< {i} {serial_no} >"] = match
                    placeholder_entity_map[f"<{i} {serial_no}]"] = match
                    placeholder_entity_map[f"< {i} {serial_no} ]"] = match
                    placeholder_entity_map[f"[{i}{serial_no}]"] = match
                    placeholder_entity_map[f"[{i} {serial_no}]"] = match
                    placeholder_entity_map[f"[ {i}{serial_no} ]"] = match
                    placeholder_entity_map[f"[ {i} {serial_no} ]"] = match
                    placeholder_entity_map[f"{i} {serial_no}"] = match
                    placeholder_entity_map[f"{i}{serial_no}"] = match

                text = text.replace(match, base_placeholder)
                serial_no += 1

        text = re.sub(r"\s+", " ", text).replace(">/", ">").replace("]/", "]")
        self._placeholder_entity_maps.put(placeholder_entity_map)
        return text

    def _normalize(self, text: str) -> Tuple[str, dict]:
        patterns = [
            self._EMAIL_PATTERN,
            self._URL_PATTERN,
            self._NUMERAL_PATTERN,
            self._OTHER_PATTERN,
        ]

        text = self._normalize_indic_numerals(text.strip())

        if self.inference:
            text = self._wrap_with_placeholders(text, patterns)

        return text

    def _apply_lang_tags(self, sent: str, src_lang: str, tgt_lang: str, delimiter=" ") -> str:
        return f"{src_lang}{delimiter}{tgt_lang}{delimiter}{sent.strip()}"

    def _preprocess(
        self,
        sent: str,
        lang: str,
        normalizer: Union[MosesPunctNormalizer, IndicNormalizerFactory],
    ) -> str:
        iso_lang = self._flores_codes.get(lang, "hi")
        sent = self._punc_norm(sent)
        sent = self._normalize(sent)

        transliterate = True
        if lang.split("_")[1] in ["Arab", "Aran", "Olck", "Mtei", "Latn"]:
            transliterate = False

        if iso_lang == "en":
            processed_sent = " ".join(
                self._en_tok.tokenize(
                    self._en_normalizer.normalize(sent.strip()), escape=False
                )
            )
        elif transliterate:
            processed_sent = self._xliterator.transliterate(
                " ".join(
                    indic_tokenize.trivial_tokenize(
                        normalizer.normalize(sent.strip()), iso_lang
                    )
                ),
                iso_lang,
                "hi",
            ).replace(" ् ", "्")
        else:
            processed_sent = " ".join(
                indic_tokenize.trivial_tokenize(
                    normalizer.normalize(sent.strip()), iso_lang
                )
            )

        return processed_sent

    def preprocess_batch(
        self,
        batch: List[str],
        src_lang: str,
        tgt_lang: str,
        is_target: bool = False,
    ) -> List[str]:
        normalizer = (
            IndicNormalizerFactory().get_normalizer(self._flores_codes.get(src_lang, "hi"))
            if src_lang != "eng_Latn"
            else None
        )

        preprocessed_sents = [
            self._preprocess(sent, src_lang, normalizer) for sent in batch
        ]

        tagged_sents = (
            [
                self._apply_lang_tags(sent, src_lang, tgt_lang)
                for sent in preprocessed_sents
            ]
            if not is_target
            else preprocessed_sents
        )

        return tagged_sents

    def _postprocess(self, sent: str, lang: str = "hin_Deva"):
        placeholder_entity_map = self._placeholder_entity_maps.get()

        if isinstance(sent, tuple) or isinstance(sent, list):
            sent = sent[0]

        lang_code, script_code = lang.split("_")
        iso_lang = self._flores_codes.get(lang, "hi")

        if script_code in ["Arab", "Aran"]:
            sent = (
                sent.replace(" ؟", "؟")
                .replace(" ۔", "۔")
                .replace(" ،", "،")
                .replace("ٮ۪", "ؠ")
            )

        if lang_code == "ory":
            sent = sent.replace("ଯ଼", "ୟ")

        for k, v in placeholder_entity_map.items():
            sent = sent.replace(k, v)

        return (
            self._en_detok.detokenize(sent.split(" "))
            if lang == "eng_Latn"
            else indic_detokenize.trivial_detokenize(
                self._xliterator.transliterate(sent, "hi", iso_lang),
                iso_lang,
            )
        )

    def postprocess_batch(self, sents: List[str], lang: str = "hin_Deva") -> List[str]:
        postprocessed_sents = [self._postprocess(sent, lang) for sent in zip(sents)]
        self._placeholder_entity_maps.queue.clear()
        return postprocessed_sents
