"""Dataset loaders. Each returns a Dataset with spans already mapped to
families (see types.py). Public sets come from Hugging Face; the two own sets
are generated (synthetic.py)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from .loaders_secrets import SECRET_LOADERS
from .types import IGNORE, Dataset, Example, Span

PII_BENCH_MAP = {
    "NAME": "PERSON", "PHONE_NUMBER": "PHONE", "EMAIL": "EMAIL", "ADDRESS": "ADDRESS",
    "BANK_CARD_NUMBER": "CARD", "CVC": "CVC", "INN": "INN", "KPP": "KPP", "OGRN": "OGRN",
    "OGRNIP": "OGRN", "SNILS": "SNILS", "PASSPORT_NUMBER": "PASSPORT", "TOKEN": "SECRET",
}

# Tags actually present in the data (the card lists only some): PER 782, STREET_ADDRESS 687,
# PERSON 209, GPE 116, THEO 50, PUBLIC_PER 39, PUBLIC_PERSON 14, PET 13, PUBLIC_PLACES 11, FICT 6, PER_PUBLIC 6.
JAYGUARD_MAP = {
    "PER": "PERSON", "PERSON": "PERSON", "PUBLIC_PER": "PERSON", "PUBLIC_PERSON": "PERSON", "PER_PUBLIC": "PERSON",
    "FICT": IGNORE, "THEO": IGNORE, "PET": IGNORE, "GPE": "ADDRESS", "STREET_ADDRESS": "ADDRESS",
    "PUBLIC_PLACES": IGNORE,
}

REDMADROBOT_MAP = {
    "FIRST_NAME": "PERSON", "LAST_NAME": "PERSON", "MIDDLE_NAME": "PERSON",
    "COUNTRY": "ADDRESS", "REGION": "ADDRESS", "DISTRICT": "ADDRESS", "CITY": "ADDRESS",
    "STREET": "ADDRESS", "HOUSE": "ADDRESS", "EMAIL": "EMAIL", "PHONE": "PHONE", "URL": "URL",
    "IP_ADDRESS": "IP", "PASSPORT": "PASSPORT", "INN": "INN", "SNILS": "SNILS", "OMS": "OMS",
    "CREDIT_CARD": "CARD", "DRIVER_LICENSE": "DRIVER_LICENSE", "MILITARY_ID": "OTHER_ID",
    "BIRTH_CERTIFICATE": "OTHER_ID",
}

def _families(mapping: dict[str, str]) -> set[str]:
    return {f for f in mapping.values() if f != IGNORE}


def load_pii_bench(limit: int | None = None) -> Dataset:
    from datasets import load_dataset

    ds = load_dataset("hivetrace/pii-bench")
    examples = [
        Example(
            r["text"],
            [Span(e["start"], e["end"], PII_BENCH_MAP[e["type"]]) for e in r["entities"]],
            "ru",
            {"domain": r["domain"], "split": split},
        )
        for split in ("domain", "entity")
        for r in ds[split]
    ]
    return Dataset("pii-bench", examples[:limit], _families(PII_BENCH_MAP), "Apache-2.0 (eval only)",
                    "hivetrace/pii-bench")


def _bio_to_spans(tokens: list[str], tags: list[str], text: str, mapping: dict[str, str]) -> list[Span]:
    """Locate each token in `text` left-to-right and fold BIO tags into spans."""
    spans: list[Span] = []
    cursor = 0
    current: tuple[int, int, str] | None = None
    lowered = text.lower()
    for token, tag in zip(tokens, tags):
        start = lowered.find(token.lower(), cursor)
        if start < 0:
            continue
        end = start + len(token)
        cursor = end
        if tag == "O" or tag not in mapping and tag[2:] not in mapping:
            if current:
                spans.append(Span(*current))
                current = None
            continue
        prefix, label = (tag[:2], tag[2:]) if tag[:2] in ("B-", "I-") else ("B-", tag)
        family = mapping[label]
        if prefix == "I-" and current and current[2] == family:
            current = (current[0], end, family)
        else:
            if current:
                spans.append(Span(*current))
            current = (start, end, family)
    if current:
        spans.append(Span(*current))
    return spans


def load_jayguard(limit: int | None = None) -> Dataset:
    from datasets import load_dataset

    ds = load_dataset("just-ai/jayguard-ner-benchmark")["train"]
    examples = []
    for r in ds:
        text = " ".join(r["tokens"])
        examples.append(Example(text, _bio_to_spans(r["tokens"], r["ner_tags"], text, JAYGUARD_MAP), "ru"))
    return Dataset("jayguard", examples[:limit], _families(JAYGUARD_MAP), "MIT / Apache-2.0 (card conflicts)",
                    "just-ai/jayguard-ner-benchmark")


def load_redmadrobot(limit: int | None = None) -> Dataset:
    from datasets import load_dataset

    ds = load_dataset("redmadrobot-rnd/pii_benchmark")["test"]
    examples = []
    for r in ds:
        tokens, tags = json.loads(r["tokens"]), json.loads(r["ner_tags"])
        examples.append(Example(r["text"], _bio_to_spans(tokens, tags, r["text"], REDMADROBOT_MAP), "ru"))
    return Dataset("redmadrobot", examples[:limit], _families(REDMADROBOT_MAP), "MIT",
                    "redmadrobot-rnd/pii_benchmark")


def load_synthetic(limit: int | None = None) -> Dataset:
    from .synthetic import generate

    examples = generate(seed=506, count=limit or 400)
    return Dataset("synthetic-ru", examples, set(f for e in examples for s in e.spans for f in [s.label]) - {IGNORE},
                    "own (generated)", "bench/buffbench/synthetic.py")


def load_secrets(limit: int | None = None) -> Dataset:
    from .synthetic import generate_secrets

    examples = generate_secrets(seed=506, count=limit or 300)
    return Dataset("secrets", examples, {"SECRET"}, "own (generated)", "bench/buffbench/synthetic.py")


LOADERS: dict[str, Callable[[int | None], Dataset]] = {
    "pii-bench": load_pii_bench,
    "jayguard": load_jayguard,
    "redmadrobot": load_redmadrobot,
    "synthetic": load_synthetic,
    "secrets": load_secrets,
    **SECRET_LOADERS,
}

WORD = re.compile(r"\w", re.UNICODE)
