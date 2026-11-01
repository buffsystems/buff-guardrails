"""Rules decide structured identifiers; NER models fill in the rest.

Presidio keeps, per entity type, the highest-scoring result and drops any
same-type result it fully contains. A model that labels `ИНН 7707083893` as
RU_INN with score 0.99 would therefore erase the checksum-validated
`7707083893` the rule found, and its wider span would win against other types
too. Capping a model's score for structured types at the analyzer threshold
keeps such a result only where no rule claimed the span; `without_overlaps`
then hands the client one span per stretch of text.
"""

from __future__ import annotations

from typing import Iterable

from presidio_analyzer import RecognizerResult

STRUCTURED_ENTITIES = frozenset({
    "RU_INN", "RU_KPP", "RU_OGRN", "RU_SNILS", "RU_OMS", "RU_PASSPORT", "RU_DRIVER_LICENSE", "RU_BIK",
    "BANK_ACCOUNT", "IBAN_CODE", "CREDIT_CARD", "CVC", "PHONE_NUMBER", "EMAIL_ADDRESS", "URL", "IP_ADDRESS",
    "SECRET", "CRYPTO",
})


def cap_structured(results: Iterable[RecognizerResult], cap: float) -> list[RecognizerResult]:
    """Lower a model's score for structured types to `cap` (the analyzer threshold)."""
    out = list(results)
    for r in out:
        if r.entity_type in STRUCTURED_ENTITIES and r.score > cap:
            r.score = cap
    return out


def without_overlaps(results: Iterable[RecognizerResult]) -> list[RecognizerResult]:
    """One span per stretch of text: Presidio keeps overlapping results of different
    types (URL inside an e-mail); clients that splice placeholders by offsets
    (LiteLLM) would corrupt the text. Highest score wins, longer span breaks ties."""
    ordered = sorted(results, key=lambda r: (-r.score, -(r.end - r.start), r.start))
    kept: list[RecognizerResult] = []
    for r in ordered:
        if all(r.end <= k.start or r.start >= k.end for k in kept):
            kept.append(r)
    return sorted(kept, key=lambda r: r.start)
