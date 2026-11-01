"""Mask / unmask with numbered placeholders.

`<PERSON_1>`, `<PHONE_NUMBER_2>` … — the same value inside one text always gets
the same placeholder, so the model can refer to it consistently and unmasking
is unambiguous. Mirrors the token format LiteLLM's presidio guardrail uses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Entity:
    type: str
    start: int
    end: int
    score: float
    original: str = ""
    placeholder: str = ""


@dataclass
class Masked:
    text: str
    entities: list[Entity]
    mapping: dict[str, str] = field(default_factory=dict)  # placeholder → original


def resolve_overlaps(entities: list[Entity]) -> list[Entity]:
    """Keep the highest-scoring span among overlapping ones (longer wins ties)."""
    ordered = sorted(entities, key=lambda e: (-e.score, -(e.end - e.start), e.start))
    kept: list[Entity] = []
    for e in ordered:
        if all(e.end <= k.start or e.start >= k.end for k in kept):
            kept.append(e)
    return sorted(kept, key=lambda e: e.start)


def mask(text: str, analyzer_results: list[dict]) -> Masked:
    entities = resolve_overlaps(
        [Entity(r["entity_type"], int(r["start"]), int(r["end"]), float(r["score"])) for r in analyzer_results]
    )
    counters: dict[str, int] = {}
    by_value: dict[tuple[str, str], str] = {}
    out: list[str] = []
    cursor = 0
    mapping: dict[str, str] = {}
    for e in entities:
        e.original = text[e.start:e.end]
        key = (e.type, e.original)
        if key not in by_value:
            counters[e.type] = counters.get(e.type, 0) + 1
            by_value[key] = f"<{e.type}_{counters[e.type]}>"
        e.placeholder = by_value[key]
        mapping[e.placeholder] = e.original
        out.append(text[cursor:e.start])
        out.append(e.placeholder)
        cursor = e.end
    out.append(text[cursor:])
    return Masked("".join(out), entities, mapping)


PLACEHOLDER_LIKE = re.compile(r"(?:[<\[{(]\s*)?\b([A-Z][A-Z_]*_\d+)\b(?:\s*[>\]})])?")


def unmask(text: str, mapping: dict[str, str]) -> str:
    """Restore originals. Models often rewrite `<PERSON_1>` as `[PERSON_1]`, `PERSON_1` or
    `{PERSON_1}`; every such spelling of a known placeholder is restored too."""
    def repl(m: re.Match[str]) -> str:
        key = f"<{m.group(1)}>"
        return mapping[key] if key in mapping else m.group(0)
    return PLACEHOLDER_LIKE.sub(repl, text)
