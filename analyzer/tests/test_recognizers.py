"""Recognizer behaviour on short sentences. Uses the rules-only engine with the
small spaCy models (needed for lemmas/context), so it runs in seconds."""

import pytest

from buff_guardrails.engine import EngineSettings, build_analyzer


@pytest.fixture(scope="module")
def analyzer():
    return build_analyzer(EngineSettings(ner="none", spacy_models={"ru": "ru_core_news_sm", "en": "en_core_web_sm"}))


def found(analyzer, text, language="ru"):
    return {(text[r.start:r.end], r.entity_type) for r in analyzer.analyze(text=text, language=language)}


def test_snils_checksum_or_context(analyzer):
    assert ("112-233-445 95", "RU_SNILS") in found(analyzer, "номер 112-233-445 95")  # valid checksum, no context
    assert ("112-233-445 96", "RU_SNILS") in found(analyzer, "СНИЛС 112-233-445 96")  # invalid, but context word
    assert not {e for e in found(analyzer, "номер 112-233-445 96") if e[1] == "RU_SNILS"}


def test_inn_12_digits_alone_and_10_digits_with_context(analyzer):
    assert ("500100732259", "RU_INN") in found(analyzer, "номер 500100732259")
    assert ("7707083893", "RU_INN") in found(analyzer, "ИНН 7707083893")
    assert ("7707083893", "RU_INN") in found(analyzer, "Vector Plus LLC, TIN 7707083893", "en")
    assert not {e for e in found(analyzer, "заказ 7707083893 отправлен") if e[1] == "RU_INN"}


def test_ogrn_card_phone_passport(analyzer):
    text = "ОГРН 1027700132195, карта 2200 1234 5678 9010, тел. +7 (912) 345-67-89, паспорт 45 09 123456"
    got = found(analyzer, text)
    assert ("1027700132195", "RU_OGRN") in got
    assert ("+7 (912) 345-67-89", "PHONE_NUMBER") in got
    assert ("45 09 123456", "RU_PASSPORT") in got


def test_cards_in_russian_text(analyzer):
    assert ("5536913756781239", "CREDIT_CARD") in found(analyzer, "Номер моей 5536913756781239 для возврата")
    assert ("2200000000000053", "CREDIT_CARD") in found(analyzer, "карта 2200000000000053")
    # invalid Luhn: only with a card context word
    assert ("4276 1234 5678 9012", "CREDIT_CARD") in found(analyzer, "данные карты: 4276 1234 5678 9012")
    assert not {e for e in found(analyzer, "номер заказа 4276 1234 5678 9012") if e[1] == "CREDIT_CARD"}


def test_snils_passport_formats_from_the_wild(analyzer):
    assert ("123 - 456 - 789 00", "RU_SNILS") in found(analyzer, "СНИЛС ( 123 - 456 - 789 00 )")
    assert not {e for e in found(analyzer, "код 123 - 456 - 789 00") if e[1] == "RU_SNILS"}
    assert ("45/12/123456", "RU_PASSPORT") in found(analyzer, "мой паспорт 45/12/123456")
    assert ("серия 3617 номер 826303", "RU_PASSPORT") in found(analyzer, "паспорт: серия 3617 номер 826303")
    assert ("789012", "RU_PASSPORT") in found(analyzer, "потерял паспорт! номер 789012")


def test_generic_tokens_need_context(analyzer):
    assert ("key_1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d", "SECRET") in found(analyzer, "вот key_1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d")
    hexstr = "6f5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c"
    assert (hexstr, "SECRET") in found(analyzer, f"одноразовый код верификации {hexstr} проверьте")
    assert not {e for e in found(analyzer, f"commit {hexstr} merged", "en") if e[1] == "SECRET"}


def test_date_of_birth_needs_context(analyzer):
    assert ("01.04.1984", "DATE_OF_BIRTH") in found(analyzer, "дата рождения 01.04.1984")
    assert not {e for e in found(analyzer, "сборка от 01.04.1984") if e[1] == "DATE_OF_BIRTH"}


@pytest.mark.parametrize(
    "text, secret",
    [
        ("export OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz0123456789", "sk-abcdefghijklmnopqrstuvwxyz0123456789"),
        ("Authorization: Bearer ghp_abcdefghijklmnopqrstuvwxyz0123456789", "ghp_abcdefghijklmnopqrstuvwxyz0123456789"),
        ("DATABASE_URL=postgres://app:S3cr3tPass@db:5432/app", "S3cr3tPass"),
        ("key = \"AKIAABCDEFGHIJKLMNOP\"", "AKIAABCDEFGHIJKLMNOP"),
        ("token 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw1", "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw1"),
    ],
)
def test_secret_value_only_is_matched(analyzer, text, secret):
    assert (secret, "SECRET") in found(analyzer, text, "en")


def test_secret_negatives(analyzer):
    got = found(analyzer, "digest = sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08 v1.2.3", "en")
    assert not {e for e in got if e[1] == "SECRET"}


def test_english_phones(analyzer):
    assert ("(415) 867-5309", "PHONE_NUMBER") in found(analyzer, "call me at (415) 867-5309", "en")
    assert ("555.123.4567", "PHONE_NUMBER") in found(analyzer, "call me at 555.123.4567", "en")
    assert not {e for e in found(analyzer, "order 4158675309 shipped", "en") if e[1] == "PHONE_NUMBER"}


def test_rules_decide_structured_types_over_a_ner_model():
    """A model that labels `ИНН 7707083893` (score 0.99) must not erase the rule's
    exact `7707083893`; its own span survives only where no rule matched."""
    from presidio_analyzer import RecognizerResult

    from buff_guardrails.hf_ner import HfTokenClassificationRecognizer
    from buff_guardrails.priority import cap_structured, without_overlaps

    hits = [RecognizerResult("RU_INN", 0, 14, 0.99), RecognizerResult("PERSON", 20, 26, 0.99)]
    capped = cap_structured(hits, 0.35)
    assert [r.score for r in capped] == [0.35, 0.99]

    text = "ИНН 7707083893, Иванов пишет 7707083893 и 1234567890 без контекста"
    engine = build_analyzer(EngineSettings(ner="none", spacy_models={"ru": "ru_core_news_sm", "en": "en_core_web_sm"}))
    class StubModel(HfTokenClassificationRecognizer):  # Presidio calls load() from __init__
        def load(self):
            self._pipeline = lambda chunk: [  # over-extends one INN and finds the context-less one
                {"entity_group": "INN", "start": 0, "end": 14, "score": 0.99},
                {"entity_group": "INN", "start": 42, "end": 52, "score": 0.99},
            ]

    model = StubModel(model_name="stub/inn", entity_mapping={"INN": "RU_INN"}, supported_language="ru")
    engine.registry.add_recognizer(model)
    results = without_overlaps(engine.analyze(text=text, language="ru"))
    spans = {(text[r.start:r.end], r.entity_type) for r in results}
    assert ("7707083893", "RU_INN") in spans  # the rule's exact span, not the model's `ИНН …`
    assert ("ИНН 7707083893", "RU_INN") not in spans
    assert ("1234567890", "RU_INN") in spans  # no rule matched here, the model fills in


def test_without_overlaps_keeps_best_span():
    from presidio_analyzer import RecognizerResult

    from buff_guardrails.priority import without_overlaps

    kept = without_overlaps([
        RecognizerResult("URL", 5, 16, 0.5),
        RecognizerResult("EMAIL_ADDRESS", 0, 16, 1.0),
        RecognizerResult("PERSON", 20, 26, 0.85),
        RecognizerResult("LOCATION", 20, 30, 0.85),
    ])
    assert [(r.entity_type, r.start, r.end) for r in kept] == [("EMAIL_ADDRESS", 0, 16), ("LOCATION", 20, 30)]
