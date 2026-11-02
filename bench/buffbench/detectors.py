"""Detector configurations under test. Every detector is the same
buff_guardrails engine with a different NER choice, so the comparison shows
what each optional model adds on top of the rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from buff_guardrails.engine import EngineSettings, build_analyzer
from buff_guardrails.gliner2_ner import Gliner2Recognizer
from buff_guardrails.hf_ner import HfTokenClassificationRecognizer
from buff_guardrails.priority import without_overlaps

from .types import DETECTOR_TO_FAMILY, Span

REDMADROBOT_MAPPING = {
    "FIRST_NAME": "PERSON", "LAST_NAME": "PERSON", "MIDDLE_NAME": "PERSON", "COUNTRY": "LOCATION",
    "REGION": "LOCATION", "DISTRICT": "LOCATION", "CITY": "LOCATION", "STREET": "ADDRESS", "HOUSE": "ADDRESS",
    "EMAIL": "EMAIL_ADDRESS", "PHONE": "PHONE_NUMBER", "URL": "URL", "IP_ADDRESS": "IP_ADDRESS",
    "PASSPORT": "RU_PASSPORT", "INN": "RU_INN", "SNILS": "RU_SNILS", "OMS": "RU_OMS", "CREDIT_CARD": "CREDIT_CARD",
    "DRIVER_LICENSE": "RU_DRIVER_LICENSE", "MILITARY_ID": "OTHER_ID", "BIRTH_CERTIFICATE": "OTHER_ID",
}

NEMOTRON_MAPPING = {
    "name": "PERSON", "first_name": "PERSON", "last_name": "PERSON", "middle_name": "PERSON", "name_initials": "PERSON",
    "address": "ADDRESS", "address_street": "ADDRESS", "address_house": "ADDRESS", "address_city": "LOCATION",
    "address_country": "LOCATION", "address_region": "LOCATION", "address_district": "LOCATION",
    "address_postal_code": "ADDRESS", "address_apartment": "ADDRESS", "address_building": "ADDRESS",
    "email": "EMAIL_ADDRESS", "mobile_phone": "PHONE_NUMBER", "ip": "IP_ADDRESS", "snils": "RU_SNILS", "tin": "RU_INN",
    "document_number": "OTHER_ID", "military_individual_number": "OTHER_ID",
}

GLINER2_PII_LABELS = {
    "person": "PERSON", "first_name": "PERSON", "last_name": "PERSON", "address": "ADDRESS", "street": "ADDRESS",
    "city": "LOCATION", "country": "LOCATION", "region": "LOCATION", "postal_code": "ADDRESS",
    "email": "EMAIL_ADDRESS", "phone": "PHONE_NUMBER", "passport": "RU_PASSPORT", "national_id": "OTHER_ID",
    "card_number": "CREDIT_CARD", "bank_account": "BANK_ACCOUNT", "date_of_birth": "DATE_OF_BIRTH",
}

GLINER_CLASSIC_LABELS = {
    "person": "PERSON", "name": "PERSON", "full address": "ADDRESS", "address": "ADDRESS", "street address": "ADDRESS",
    "city": "LOCATION", "country": "LOCATION", "email": "EMAIL_ADDRESS", "phone number": "PHONE_NUMBER",
    "passport number": "RU_PASSPORT", "credit card number": "CREDIT_CARD", "date of birth": "DATE_OF_BIRTH",
    "bank account number": "BANK_ACCOUNT", "social security number": "OTHER_ID",
}


@dataclass
class Detector:
    name: str
    description: str
    settings: EngineSettings
    extra: Callable[[str], object] | None = None  # language → extra recognizer (or a list of them)
    entities: list[str] | None = None
    without_secret_rules: bool = False  # drop the shipped secret regexes (a model alone)
    _analyzer: object = field(default=None, repr=False)

    def load(self) -> None:
        analyzer = build_analyzer(self.settings)
        if self.without_secret_rules:
            for recognizer in list(analyzer.registry.recognizers):
                if recognizer.name.startswith("buff_secret_"):
                    analyzer.registry.remove_recognizer(recognizer.name)
        if self.extra:
            for language in self.settings.languages:
                made = self.extra(language)
                for recognizer in made if isinstance(made, list) else [made]:
                    analyzer.registry.add_recognizer(recognizer)
        self._analyzer = analyzer

    def analyze(self, text: str, language: str) -> list[Span]:
        results = self._analyzer.analyze(text=text, language=language, entities=self.entities)  # type: ignore[attr-defined]
        return [  # one span per stretch of text, as the analyzer service returns it

            Span(r.start, r.end, DETECTOR_TO_FAMILY[r.entity_type])
            for r in without_overlaps(results)
            if r.entity_type in DETECTOR_TO_FAMILY
        ]


def _settings(ner: str = "spacy", **kw) -> EngineSettings:
    return EngineSettings(ner=ner, **kw)


def _hf(model: str, mapping: dict[str, str]) -> Callable[[str], object]:
    return lambda lang: HfTokenClassificationRecognizer(model_name=model, entity_mapping=mapping, supported_language=lang)


def _gliner2(model: str, mapping: dict[str, str], threshold: float = 0.4) -> Callable[[str], object]:
    return lambda lang: Gliner2Recognizer(model_name=model, entity_mapping=mapping, supported_language=lang, threshold=threshold)


DETECTORS: dict[str, Detector] = {
    "rules": Detector("rules", "regex + checksums only, no NER (spaCy sm for context words)", _settings("none")),
    "spacy-lg": Detector("spacy-lg", "rules + spaCy ru_core_news_lg / en_core_web_lg NER (kit default)", _settings("spacy")),
    "spacy-md": Detector("spacy-md", "rules + spaCy *_md NER", _settings("spacy", spacy_models={"ru": "ru_core_news_md", "en": "en_core_web_md"})),
    "gliner-multi-pii": Detector(
        "gliner-multi-pii", "rules + urchade/gliner_multi_pii-v1 (Presidio GLiNERRecognizer)",
        _settings("none", gliner_model="urchade/gliner_multi_pii-v1"),
    ),
    "gliner2-pii-multi": Detector(
        "gliner2-pii-multi", "rules + fastino/gliner2-privacy-filter-PII-multi",
        _settings("none"), _gliner2("fastino/gliner2-privacy-filter-PII-multi", GLINER2_PII_LABELS),
    ),
    "gliner-guard-omni": Detector(
        "gliner-guard-omni", "rules + hivetrace/gliner-guard-omni (GLiNER2, ru+en)",
        _settings("none"), _gliner2("hivetrace/gliner-guard-omni", GLINER2_PII_LABELS),
    ),
    "rubert-redmadrobot": Detector(
        "rubert-redmadrobot", "rules + redmadrobot-rnd/rubert-base-pii-ner (ruBERT, 21 RU PII types)",
        _settings("none"), _hf("redmadrobot-rnd/rubert-base-pii-ner", REDMADROBOT_MAPPING),
    ),
    "distilbert-pii-guard": Detector(
        "distilbert-pii-guard", "rules + aule13/pii-guard-distilbert (multilingual DistilBERT, RU PII)",
        _settings("none"), _hf("aule13/pii-guard-distilbert", REDMADROBOT_MAPPING),
    ),
    "nemotron-xlmr": Detector(
        "nemotron-xlmr", "rules + scanpatch/pii-ner-nemotron (XLM-R large, ru/en/uk)",
        _settings("none"), _hf("scanpatch/pii-ner-nemotron", NEMOTRON_MAPPING),
    ),
    "spacy-lg+rubert": Detector(
        "spacy-lg+rubert", "rules + spaCy lg + ruBERT redmadrobot (union)",
        _settings("spacy"), _hf("redmadrobot-rnd/rubert-base-pii-ner", REDMADROBOT_MAPPING),
    ),
}
