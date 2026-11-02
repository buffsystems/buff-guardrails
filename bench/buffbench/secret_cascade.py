"""Cascades and ensembles of the secret detectors.

A cascade keeps what the regexes are sure about (provider key formats, JWT, PEM,
password in a URL: pattern score ≥ `confident`) and hands every weaker regex
candidate (assignment, bearer, Russian key word, opaque blob) to a model judge:
bardsai scores the exact span in its context; cbx confirms by overlap. The
judge's own findings are added unless `own_scan` is off. An ensemble is the
plain union of two models.
"""

from __future__ import annotations

from presidio_analyzer import RecognizerResult

from buff_guardrails.secrets import SECRET_CONTEXT, build_secret_recognizer

from .secret_recognizers import BardsaiRecognizer, CbxRecognizer, ExternalSecretRecognizer, Hit
from .secret_rules_ext import build_secret_ext_recognizer

RU_CONTEXT = tuple(w for w in SECRET_CONTEXT if any("а" <= ch <= "я" for ch in w))


def _overlaps(s: int, e: int, spans: list[Hit]) -> bool:
    return any(a < e and s < b for a, b, _ in spans)


class CascadeRecognizer(ExternalSecretRecognizer):
    def __init__(self, supported_language: str, *, judges: tuple[str, ...] = ("bardsai",), judge_threshold: float = 0.3,
                 confident: float = 0.85, own_scan: bool = True, ext: bool = True,
                 trust: tuple[str, ...] = ("ru_keyword_value",), ext_builder=build_secret_ext_recognizer,
                 name: str = "cascade") -> None:
        """`trust`: pattern names kept without a judge — the models know no Russian, so a
        value right after «пароль:» would always be rejected by them."""
        self.judges, self.judge_threshold, self.confident, self.own_scan, self.ext = judges, judge_threshold, confident, own_scan, ext
        self.trust = set(trust)
        self.ext_builder = ext_builder
        super().__init__(supported_language, f"{name}_{supported_language}")

    def _sure(self, r: RecognizerResult, text: str) -> bool:
        """Confident score, a trusted pattern, or a Russian context word right before the
        span (the analyzer's context boost is what makes «токен: <blob>» a hit; the
        models cannot re-judge Russian context, so such candidates are kept)."""
        pattern = getattr(r.analysis_explanation, "pattern_name", None)
        if r.score >= self.confident or pattern in self.trust:
            return True
        before = text[max(0, r.start - 60):r.start].lower()
        return any(word in before for word in RU_CONTEXT)

    def _load(self) -> None:
        lang = self.supported_language
        self._rules = [build_secret_recognizer(lang)] + ([self.ext_builder(lang)] if self.ext else [])
        self._bardsai = BardsaiRecognizer(lang) if "bardsai" in self.judges else None
        self._cbx = CbxRecognizer(lang) if "cbx" in self.judges else None
        for model in (self._bardsai, self._cbx):
            if model:
                model.load()

    def _candidates(self, text: str) -> list[RecognizerResult]:
        out: list[RecognizerResult] = []
        for rec in self._rules:
            out.extend(rec.analyze(text, ["SECRET"]))
        return out

    def _scan(self, text: str) -> list[Hit]:
        cands = self._candidates(text)
        hits: list[Hit] = [(r.start, r.end, max(r.score, self.confident)) for r in cands if self._sure(r, text)]
        weak = [(r.start, r.end) for r in cands if not self._sure(r, text)]
        own: list[Hit] = []
        if self._bardsai:
            if weak:
                probs, _ = self._bardsai._det.score_spans(text, weak)
                hits += [(s, e, float(p)) for (s, e), p in zip(weak, probs) if p >= self.judge_threshold]
            if self.own_scan:
                own += self._bardsai._scan(text)
        if self._cbx:
            cbx_hits = self._cbx._scan(text)
            hits += [(s, e, 0.6) for s, e in weak if _overlaps(s, e, cbx_hits)]
            if self.own_scan:
                own += cbx_hits
        return hits + own


class UnionRecognizer(ExternalSecretRecognizer):
    """Plain union of model detectors (no regexes)."""

    def __init__(self, supported_language: str, members: tuple[str, ...] = ("bardsai", "cbx")) -> None:
        self.members = members
        super().__init__(supported_language, "union_" + "_".join(members) + f"_{supported_language}")

    def _load(self) -> None:
        lang = self.supported_language
        self._models = [BardsaiRecognizer(lang) if m == "bardsai" else CbxRecognizer(lang) for m in self.members]
        for model in self._models:
            model.load()

    def _scan(self, text: str) -> list[Hit]:
        return [h for model in self._models for h in model._scan(text)]
