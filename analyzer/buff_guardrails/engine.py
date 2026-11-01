"""Build the Presidio AnalyzerEngine from environment settings.

One place decides which NER runs. Everything is CPU by default:

  GUARDRAILS_LANGUAGES      comma list, default "ru,en"
  GUARDRAILS_SPACY_RU/EN    spaCy model per language (default *_lg)
  GUARDRAILS_NER            "spacy" (default) or "none" — the base NER for
                            names/locations
  GUARDRAILS_GLINER_MODEL   optional GLiNER model id → adds GLiNERRecognizer
  GUARDRAILS_HF_NER_MODEL   optional HF token-classification model id
  GUARDRAILS_HF_NER_MAPPING optional "LABEL=ENTITY,LABEL2=ENTITY2" for that model
  GUARDRAILS_DICTIONARY     path to the corporate dictionary YAML
  GUARDRAILS_SCORE_THRESHOLD default 0.35
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import PhoneRecognizer

from .dictionary import load_dictionary
from .hf_ner import HfTokenClassificationRecognizer
from .priority import cap_structured
from .ru_ids import RU_ID_SPECS
from .secrets import build_secret_recognizer

SPACY_DEFAULTS = {"ru": "ru_core_news_lg", "en": "en_core_web_lg"}
SPACY_SMALL = {"ru": "ru_core_news_sm", "en": "en_core_web_sm"}
# libphonenumber regions tried for free-form numbers. RU is deliberately absent:
# any bare 10-digit number is a "valid" Russian national number, which would turn
# every order id / ИНН into a phone. Our regexes cover the +7 / 8 forms instead.
PHONE_REGIONS = ("US", "GB", "DE", "FR", "KZ", "BY", "UA")


class WeakPhoneRecognizer(PhoneRecognizer):
    """libphonenumber matches capped below the threshold: a bare run of digits
    counts as a phone only next to a context word (phone, call, тел…);
    formatted numbers are caught by our regex patterns at full score."""

    def analyze(self, text, entities, nlp_artifacts=None):  # type: ignore[override]
        results = super().analyze(text, entities, nlp_artifacts)
        for result in results:
            result.score = min(result.score, 0.3)
        return results

# Presidio predefined recognizers we keep (the rest overlap with ours or are
# US/UK-specific and only add noise on Russian text).
KEEP_PREDEFINED = {
    "EmailRecognizer",
    "IpRecognizer",
    "UrlRecognizer",
    "IbanRecognizer",
    "CreditCardRecognizer",
    "SpacyRecognizer",
    "CryptoRecognizer",
}

GLINER_DEFAULT_MAPPING = {
    "person": "PERSON",
    "name": "PERSON",
    "first_name": "PERSON",
    "last_name": "PERSON",
    "address": "ADDRESS",
    "street address": "ADDRESS",
    "location": "LOCATION",
    "city": "LOCATION",
    "organization": "ORGANIZATION",
    "date of birth": "DATE_OF_BIRTH",
    "date_of_birth": "DATE_OF_BIRTH",
}


@dataclass
class EngineSettings:
    languages: list[str] = field(default_factory=lambda: ["ru", "en"])
    spacy_models: dict[str, str] = field(default_factory=lambda: dict(SPACY_DEFAULTS))
    ner: str = "spacy"
    gliner_model: str | None = None
    hf_ner_model: str | None = None
    hf_ner_mapping: dict[str, str] = field(default_factory=dict)
    dictionary: str | None = None
    score_threshold: float = 0.35

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "EngineSettings":
        e = os.environ if env is None else env
        languages = [x.strip() for x in e.get("GUARDRAILS_LANGUAGES", "ru,en").split(",") if x.strip()]
        spacy_models = {
            lang: e.get(f"GUARDRAILS_SPACY_{lang.upper()}", SPACY_DEFAULTS.get(lang, f"{lang}_core_news_sm"))
            for lang in languages
        }
        mapping = dict(
            pair.split("=", 1)
            for pair in e.get("GUARDRAILS_HF_NER_MAPPING", "").split(",")
            if "=" in pair
        )
        return cls(
            languages=languages,
            spacy_models=spacy_models,
            ner=e.get("GUARDRAILS_NER", "spacy"),
            gliner_model=e.get("GUARDRAILS_GLINER_MODEL") or None,
            hf_ner_model=e.get("GUARDRAILS_HF_NER_MODEL") or None,
            hf_ner_mapping=mapping,
            dictionary=e.get("GUARDRAILS_DICTIONARY") or None,
            score_threshold=float(e.get("GUARDRAILS_SCORE_THRESHOLD", "0.35")),
        )


def build_nlp_engine(settings: EngineSettings):
    # With NER off we still need spaCy for tokenisation/lemmas (context words),
    # so the small models are loaded and SpacyRecognizer is dropped below.
    models = settings.spacy_models if settings.ner == "spacy" else {
        lang: SPACY_SMALL.get(lang, model) for lang, model in settings.spacy_models.items()
    }
    configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": lang, "model_name": name} for lang, name in models.items()],
        "ner_model_configuration": {
            "model_to_presidio_entity_mapping": {
                "PER": "PERSON",
                "PERSON": "PERSON",
                "LOC": "LOCATION",
                "GPE": "LOCATION",
                "FAC": "LOCATION",
                "ORG": "ORGANIZATION",
                "NORP": "NRP",
            },
            "low_confidence_score_multiplier": 0.4,
            "low_score_entity_names": ["ORGANIZATION", "NRP"],
            "labels_to_ignore": ["CARDINAL", "ORDINAL", "QUANTITY", "PERCENT", "MONEY", "TIME", "DATE", "EVENT",
                                 "LANGUAGE", "LAW", "PRODUCT", "WORK_OF_ART"],
        },
    }
    return NlpEngineProvider(nlp_configuration=configuration).create_engine()


def build_registry(settings: EngineSettings, nlp_engine) -> RecognizerRegistry:
    registry = RecognizerRegistry(supported_languages=settings.languages)
    registry.load_predefined_recognizers(languages=settings.languages, nlp_engine=nlp_engine)
    for recognizer in list(registry.recognizers):
        if type(recognizer).__name__ not in KEEP_PREDEFINED:
            registry.remove_recognizer(recognizer.name)
        elif settings.ner != "spacy" and type(recognizer).__name__ == "SpacyRecognizer":
            registry.remove_recognizer(recognizer.name)
    for language in settings.languages:
        for build in RU_ID_SPECS:
            registry.add_recognizer(build(language))
        registry.add_recognizer(build_secret_recognizer(language))
        registry.add_recognizer(
            WeakPhoneRecognizer(
                supported_language=language,
                supported_regions=PHONE_REGIONS,
                name=f"phone_lib_{language}",
                context=["тел", "телефон", "phone", "mobile", "моб", "call", "whatsapp", "telegram"],
            )
        )
        if settings.gliner_model:
            registry.add_recognizer(_gliner(settings.gliner_model, language, settings.score_threshold))
        if settings.hf_ner_model:
            registry.add_recognizer(
                HfTokenClassificationRecognizer(
                    model_name=settings.hf_ner_model,
                    entity_mapping=settings.hf_ner_mapping,
                    supported_language=language,
                    structured_score_cap=settings.score_threshold,
                )
            )
    for recognizer in load_dictionary(settings.dictionary, settings.languages):
        registry.add_recognizer(recognizer)
    return registry


def _gliner(model_name: str, language: str, structured_score_cap: float):
    from presidio_analyzer.predefined_recognizers import GLiNERRecognizer

    class CappedGLiNERRecognizer(GLiNERRecognizer):
        def analyze(self, *args, **kwargs):
            return cap_structured(super().analyze(*args, **kwargs), structured_score_cap)

    return CappedGLiNERRecognizer(
        model_name=model_name,
        entity_mapping=GLINER_DEFAULT_MAPPING,
        supported_language=language,
        name=f"gliner_{language}",
        flat_ner=False,
        multi_label=True,
        map_location="cpu",
    )


def build_analyzer(settings: EngineSettings | None = None) -> AnalyzerEngine:
    settings = settings or EngineSettings.from_env()
    nlp_engine = build_nlp_engine(settings)
    registry = build_registry(settings, nlp_engine)
    return AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=settings.languages,
        default_score_threshold=settings.score_threshold,
    )
