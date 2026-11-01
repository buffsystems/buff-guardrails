"""Pattern recognizers for Russian identifiers, cards and contacts.

Every recognizer is registered for both `ru` and `en`, so mixed-language text
(a Russian chat quoting an English log) is covered by one engine.

Scoring convention (threshold is 0.35, a context word adds +0.35):
  * checksum-valid identifiers score on their own (0.5–0.6);
  * weak shapes (a bare 10-digit ИНН, a 6-digit passport number, an ID with a
    failed/absent checksum) score below the threshold and need a context word
    nearby — "паспорт", "СНИЛС", "карта" — to be masked.
"""

from __future__ import annotations

import re
from typing import Callable, Optional

from presidio_analyzer import Pattern, PatternRecognizer

from . import checksums

DIGITS = re.compile(r"\D")
SEP = r"[\s\-.?*]*"  # separators seen in the wild: spaces, dashes, dots, typos


class ChecksumRecognizer(PatternRecognizer):
    """PatternRecognizer whose matches must pass a checksum.

    A failed checksum drops the match (False). A passed one keeps the pattern's
    own score (None) instead of Presidio's default jump to 1.0, so weak formats
    still need a context word to clear the threshold.
    """

    def __init__(self, *, validator: Callable[[str], bool], **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._validator = validator

    def validate_result(self, pattern_text: str) -> Optional[bool]:
        return None if self._validator(DIGITS.sub("", pattern_text)) else False


def _spec(entity: str, patterns: list[Pattern], context: list[str], validator=None, tag: str = ""):
    def build(language: str) -> PatternRecognizer:
        kwargs = dict(
            supported_entity=entity,
            name=f"buff_{entity.lower()}{tag}_{language}",
            supported_language=language,
            patterns=patterns,
            context=context,
        )
        if validator is None:
            return PatternRecognizer(**kwargs)
        return ChecksumRecognizer(validator=validator, **kwargs)

    return build


CARD16 = rf"\b\d{{4}}{SEP}\d{{4}}{SEP}\d{{4}}{SEP}\d{{4}}\b"
CARD_CTX = ["карт", "card", "visa", "mastercard", "мир", "maestro", "unionpay", "оплат", "pay", "списал", "перевод"]
SNILS_SHAPE = rf"\b\d{{3}}{SEP}\d{{3}}{SEP}\d{{3}}{SEP}\d{{2}}\b"
SNILS_CTX = ["снилс", "snils", "страховой", "пенсион", "лицевой"]
OMS_CTX = ["омс", "полис", "страхов", "oms", "енп"]
PASSPORT_CTX = ["паспорт", "passport", "серия", "номер", "выдан", "паспрт"]

RU_ID_SPECS = [
    # --- checksum-validated shapes
    _spec("RU_SNILS", [Pattern("snils", SNILS_SHAPE, 0.6)], SNILS_CTX, checksums.snils),
    _spec(
        "RU_INN",
        [
            # 12 digits carry two control digits (~1% false pass) — accepted alone;
            # 10 digits carry one (~10%) — need a context word to clear the threshold.
            Pattern("inn12", r"\b\d(?:\s?\d){11}\b", 0.5),
            Pattern("inn10", r"\b\d(?:\s?\d){9}\b", 0.3),
        ],
        ["инн", "inn", "tin", "налог", "tax", "юрлиц"],
        checksums.inn,
    ),
    _spec(
        "RU_OGRN",
        [Pattern("ogrn", r"\b\d{13}\b|\b\d{15}\b", 0.5)],
        ["огрн", "огрнип", "ogrn", "егрюл", "егрип"],
        checksums.ogrn,
    ),
    _spec("CREDIT_CARD", [Pattern("card16_luhn", CARD16, 0.6),
                          Pattern("card15_luhn", rf"\b\d{{4}}{SEP}\d{{6}}{SEP}\d{{5}}\b", 0.5)],
          CARD_CTX, checksums.luhn),
    _spec("RU_OMS", [Pattern("oms_luhn", CARD16, 0.3)], OMS_CTX, checksums.luhn),
    # --- the same shapes without a valid checksum: masked only next to a context word
    _spec("RU_SNILS", [Pattern("snils_shape", SNILS_SHAPE, 0.1)], SNILS_CTX, tag="_weak"),
    _spec("CREDIT_CARD", [Pattern("card_shape", CARD16, 0.15)], CARD_CTX, tag="_weak"),
    _spec("RU_OMS", [Pattern("oms_shape", CARD16, 0.1)], OMS_CTX, tag="_weak"),
    # --- shapes without any checksum
    _spec("RU_KPP", [Pattern("kpp", r"\b\d{4}[\dA-Z]{2}\d{3}\b", 0.2)], ["кпп", "kpp"]),
    _spec(
        "RU_PASSPORT",
        [
            Pattern("passport_full", r"\b\d{2}[\s/\-]?\d{2}\s?[-/№N]?\s?\d{6}\b", 0.3),
            Pattern("passport_series_number", r"(?i)серия\s*:?\s*\d{4}\s*(?:,|и)?\s*номер(?:ом)?\s*:?\s*\d{6}", 0.6),
            Pattern("passport_number_only", r"\b\d{6}\b", 0.05),
            Pattern("passport_series_only", r"\b\d{4}\b", 0.02),
        ],
        PASSPORT_CTX,
    ),
    _spec(
        "RU_DRIVER_LICENSE",
        [Pattern("driver", r"\b\d{2}\s?[\dА-Я]{2}\s?\d{6}\b", 0.2)],
        ["водительск", "удостоверен", "права", "driver", "licen"],
    ),
    _spec("RU_BIK", [Pattern("bik", r"\b04\d{7}\b", 0.4)], ["бик", "bik", "банк"]),
    _spec(
        "BANK_ACCOUNT",
        [Pattern("account20", r"\b\d{20}\b", 0.3)],
        ["счет", "счёт", "р/с", "к/с", "расчетный", "корреспондентский", "account", "iban"],
    ),
    _spec(
        "CVC",
        [Pattern("cvc", r"\b\d{3}\b", 0.05)],
        ["cvc", "cvv", "cvc2", "cvv2", "цвс", "код безопасности", "security code", "оборот", "обратн", "код подтверждения",
         "три цифры"],
    ),
    _spec(
        "PHONE_NUMBER",
        [
            Pattern(
                "ru_phone",
                r"(?<!\d)(?:\+\s?7|8)[\s(\-]*\d{3}[\s)\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)",
                0.7,
            ),
            Pattern(
                "ru_phone_national",
                r"(?<!\d)\(?\d{3}\)?[\s\-]\d{3}[\s\-]\d{2}[\s\-]\d{2}(?!\d)",
                0.4,
            ),
            Pattern(
                "intl_phone",
                r"(?<!\d)\+\d{1,3}[\s(-]*\d{2,4}[\s)-]*\d{2,4}[\s-]*\d{2,4}(?:[\s-]*\d{2,4})?(?!\d)",
                0.5,
            ),
            # North-American style with explicit separators (bare 10 digits are not a phone here)
            Pattern("nanp_phone", r"(?<!\d)\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)", 0.4),
        ],
        ["тел", "телефон", "phone", "mobile", "моб", "звон", "call", "whatsapp", "telegram", "номер"],
    ),
    _spec(
        "DATE_OF_BIRTH",
        [
            Pattern(
                "dob_numeric",
                r"\b(?:0?[1-9]|[12]\d|3[01])[./-](?:0?[1-9]|1[012])[./-](?:19|20)\d{2}\b",
                0.2,
            ),
            Pattern(
                "dob_words_ru",
                r"\b(?:0?[1-9]|[12]\d|3[01])\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(?:19|20)\d{2}",
                0.3,
            ),
        ],
        # Presidio matches context words as substrings of spaCy lemmas:
        # рождения→рождение, родился→родиться, born→bear.
        ["рожден", "родит", "дата рождения", "born", "bear", "birth", "dob", "birthday"],
    ),
]
