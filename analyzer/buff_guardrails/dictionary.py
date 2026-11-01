"""Corporate dictionary: deny-list recognizers from a YAML file.

The file is the organisation's own list of names it never wants to leave the
perimeter: customers, project code names, contract numbers, internal domains.
Format (see conf/dictionary.example.yaml):

    entities:
      CORP_CUSTOMER: ["Ромашка", "ООО Вектор"]
      CORP_PROJECT: ["Project Falcon"]
      CORP_DOMAIN:
        regex: ["[a-z0-9.-]+\\.corp\\.example\\b"]
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml
from presidio_analyzer import Pattern, PatternRecognizer


def load_dictionary(path: Path | str | None, languages: Iterable[str]) -> list[PatternRecognizer]:
    if not path:
        return []
    file = Path(path)
    if not file.exists():
        return []
    spec = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    recognizers: list[PatternRecognizer] = []
    for entity, value in (spec.get("entities") or {}).items():
        terms: list[str] = []
        regexes: list[str] = []
        if isinstance(value, list):
            terms = [str(v) for v in value]
        elif isinstance(value, dict):
            terms = [str(v) for v in value.get("terms", [])]
            regexes = [str(v) for v in value.get("regex", [])]
        for language in languages:
            recognizers.extend(_build(entity, terms, regexes, language))
    return recognizers


def _build(entity: str, terms: list[str], regexes: list[str], language: str) -> list[PatternRecognizer]:
    built: list[PatternRecognizer] = []
    if terms:
        built.append(
            PatternRecognizer(
                supported_entity=entity,
                name=f"dict_{entity.lower()}_terms_{language}",
                supported_language=language,
                deny_list=terms,
                deny_list_score=0.9,
            )
        )
    if regexes:
        built.append(
            PatternRecognizer(
                supported_entity=entity,
                name=f"dict_{entity.lower()}_regex_{language}",
                supported_language=language,
                patterns=[Pattern(f"{entity}_{i}", rx, 0.8) for i, rx in enumerate(regexes)],
            )
        )
    return built
