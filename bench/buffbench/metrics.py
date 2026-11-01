"""Scoring: per-family exact-span and character-level P/R/F1, plus two
setup-level numbers — leak (PII characters left unmasked) and overmask
(non-PII characters masked). Latency is collected by the runner."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from .types import IGNORE, Example, Span

TRIM = re.compile(r"^[\s\W_]+|[\s\W_]+$", re.UNICODE)
GAP = re.compile(r"^[\s,.;:()«»\"'\-–—/]*$")


def normalise(spans: list[Span], text: str, families: set[str]) -> list[Span]:
    """Trim punctuation, keep scored families, merge adjacent same-family spans."""
    kept: list[Span] = []
    for s in spans:
        if s.label not in families:
            continue
        piece = text[s.start:s.end]
        lead = len(piece) - len(piece.lstrip(" \t\n\r,.;:()«»\"'"))
        trail = len(piece) - len(piece.rstrip(" \t\n\r,.;:()«»\"'"))
        start, end = s.start + lead, s.end - trail
        if end > start:
            kept.append(Span(start, end, s.label))
    kept.sort(key=lambda s: (s.start, s.end))
    merged: list[Span] = []
    for s in kept:
        if merged and merged[-1].label == s.label and s.start <= merged[-1].end + 3 and GAP.match(
            text[merged[-1].end:s.start]
        ):
            merged[-1] = Span(merged[-1].start, max(merged[-1].end, s.end), s.label)
        else:
            merged.append(s)
    return merged


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, other: "Counts") -> None:
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


@dataclass
class Scores:
    exact: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    chars: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    any_chars: Counts = field(default_factory=Counts)  # type-agnostic: leak / overmask

    def add(self, other: "Scores") -> None:
        for k, v in other.exact.items():
            self.exact[k].add(v)
        for k, v in other.chars.items():
            self.chars[k].add(v)
        self.any_chars.add(other.any_chars)

    @property
    def leak(self) -> float:
        return 1 - self.any_chars.recall

    @property
    def overmask(self) -> float:
        c = self.any_chars
        return c.fp / (c.tp + c.fp) if c.tp + c.fp else 0.0


def score_example(example: Example, predicted: list[Span], families: set[str]) -> Scores:
    text = example.text
    ignored = {i for s in example.spans if s.label == IGNORE for i in range(s.start, s.end)}
    gold = normalise(example.spans, text, families)
    pred = [p for p in normalise(predicted, text, families) if not any(i in ignored for i in range(p.start, p.end))]
    scores = Scores()
    gold_set = {(s.start, s.end, s.label) for s in gold}
    pred_set = {(s.start, s.end, s.label) for s in pred}
    for fam in families:
        g = {x for x in gold_set if x[2] == fam}
        p = {x for x in pred_set if x[2] == fam}
        scores.exact[fam] = Counts(tp=len(g & p), fp=len(p - g), fn=len(g - p))
        gc = {i for s in gold if s.label == fam for i in range(s.start, s.end)}
        pc = {i for s in pred if s.label == fam for i in range(s.start, s.end)}
        scores.chars[fam] = Counts(tp=len(gc & pc), fp=len(pc - gc), fn=len(gc - pc))
    gall = {i for s in gold for i in range(s.start, s.end)}
    pall = {i for s in pred for i in range(s.start, s.end)}
    scores.any_chars = Counts(tp=len(gall & pall), fp=len(pall - gall), fn=len(gall - pall))
    return scores
