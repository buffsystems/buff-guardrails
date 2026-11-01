"""Shared types and the canonical entity families used for scoring.

Every dataset label and every detector label is mapped to one FAMILY. Scoring
happens per family, and only on the families a dataset annotates; a family a
dataset never labels is dropped from predictions, not counted as a false
positive. `IGNORE` marks gold spans we exclude from both sides (out of scope,
e.g. AGE or fictional characters).
"""

from __future__ import annotations

from dataclasses import dataclass, field

IGNORE = "IGNORE"

FAMILIES = [
    "PERSON", "ADDRESS", "PHONE", "EMAIL", "CARD", "CVC", "INN", "KPP", "OGRN", "SNILS",
    "PASSPORT", "OMS", "DRIVER_LICENSE", "SECRET", "URL", "IP", "DOB", "ACCOUNT", "BIK",
    "OTHER_ID",
]

# Presidio / detector entity → family
DETECTOR_TO_FAMILY: dict[str, str] = {
    "PERSON": "PERSON",
    "LOCATION": "ADDRESS",
    "ADDRESS": "ADDRESS",
    "PHONE_NUMBER": "PHONE",
    "EMAIL_ADDRESS": "EMAIL",
    "CREDIT_CARD": "CARD",
    "CVC": "CVC",
    "RU_INN": "INN",
    "RU_KPP": "KPP",
    "RU_OGRN": "OGRN",
    "RU_SNILS": "SNILS",
    "RU_PASSPORT": "PASSPORT",
    "RU_OMS": "OMS",
    "RU_DRIVER_LICENSE": "DRIVER_LICENSE",
    "SECRET": "SECRET",
    "CRYPTO": "SECRET",
    "URL": "URL",
    "IP_ADDRESS": "IP",
    "DATE_OF_BIRTH": "DOB",
    "BANK_ACCOUNT": "ACCOUNT",
    "IBAN_CODE": "ACCOUNT",
    "RU_BIK": "BIK",
    "OTHER_ID": "OTHER_ID",
}


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    label: str  # family (or IGNORE)


@dataclass
class Example:
    text: str
    spans: list[Span]
    language: str
    meta: dict = field(default_factory=dict)


@dataclass
class Dataset:
    name: str
    examples: list[Example]
    families: set[str]  # families this dataset annotates
    licence: str
    source: str
