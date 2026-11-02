"""The secret cascade chosen by the #740 benchmark (avg F1 0.87 vs 0.64 for
the regexes alone, false spans on real agent output 90 vs 426).

Regex candidates come first. What the regexes are sure about is kept: a
pattern score of `confident` or more (provider formats, PEM, env PASSWORD=),
a trusted pattern («пароль: …»), or a Russian context word right before the
span — the model knows no Russian and would reject every such value. Every
weaker candidate (`name = value`, bearer, opaque blobs) is scored in context
by the judge and kept from `judge_threshold`. The judge's own scan is added
unless `own_scan` is off (the strict mode: fewer false spans, lower recall).
"""

from __future__ import annotations

from typing import Iterable, Optional, Protocol

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

from .secrets import SECRET_CONTEXT, SECRET_ENTITY

RU_CONTEXT = tuple(w for w in SECRET_CONTEXT if any("а" <= ch <= "я" for ch in w))
Hit = tuple[int, int, float]


class Judge(Protocol):
    def score_spans(self, text: str, spans: list[tuple[int, int]]) -> list[float]: ...

    def scan(self, text: str) -> list[Hit]: ...


class CascadeSecretRecognizer(EntityRecognizer):
    def __init__(self, language: str, rules: list[EntityRecognizer], judge: Judge, *, judge_threshold: float = 0.5,
                 confident: float = 0.85, own_scan: bool = True, trust: tuple[str, ...] = ("ru_keyword_value",)) -> None:
        self.rules, self.judge = rules, judge
        self.judge_threshold, self.confident, self.own_scan, self.trust = judge_threshold, confident, own_scan, set(trust)
        super().__init__(supported_entities=[SECRET_ENTITY], supported_language=language, name=f"buff_secret_cascade_{language}")

    def load(self) -> None:
        pass

    def _sure(self, r: RecognizerResult, text: str) -> bool:
        pattern = getattr(r.analysis_explanation, "pattern_name", None)
        if r.score >= self.confident or pattern in self.trust:
            return True
        before = text[max(0, r.start - 60):r.start].lower()
        return any(word in before for word in RU_CONTEXT)

    def analyze(self, text: str, entities: Iterable[str], nlp_artifacts: Optional[NlpArtifacts] = None) -> list[RecognizerResult]:
        candidates = [r for rule in self.rules for r in rule.analyze(text, [SECRET_ENTITY])]
        hits: list[Hit] = [(r.start, r.end, max(r.score, self.confident)) for r in candidates if self._sure(r, text)]
        weak = [(r.start, r.end) for r in candidates if not self._sure(r, text)]
        if weak:
            probs = self.judge.score_spans(text, weak)
            hits += [(s, e, p) for (s, e), p in zip(weak, probs) if p >= self.judge_threshold]
        if self.own_scan:
            hits += self.judge.scan(text)
        return [RecognizerResult(SECRET_ENTITY, s, e, score) for s, e, score in hits if e > s]
