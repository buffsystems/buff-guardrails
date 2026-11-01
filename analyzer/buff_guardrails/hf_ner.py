"""Presidio recognizer backed by a Hugging Face token-classification model.

Used for the optional self-hosted NER models (e.g. a ruBERT PII model). The
model's labels are mapped to Presidio entities with `entity_mapping`; labels
missing from the mapping are ignored. Long texts are processed in overlapping
windows so the model's max length is never exceeded.
"""

from __future__ import annotations

from typing import Iterable, Optional

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

from .priority import cap_structured


class HfTokenClassificationRecognizer(EntityRecognizer):
    def __init__(
        self,
        *,
        model_name: str,
        entity_mapping: dict[str, str],
        supported_language: str,
        name: Optional[str] = None,
        window_chars: int = 1500,
        overlap_chars: int = 200,
        device: int = -1,
        structured_score_cap: float = 0.35,
    ) -> None:
        self.model_name = model_name
        self.structured_score_cap = structured_score_cap
        self.entity_mapping = entity_mapping
        self.window_chars = window_chars
        self.overlap_chars = overlap_chars
        self._device = device
        self._pipeline = None
        super().__init__(
            supported_entities=sorted(set(entity_mapping.values())),
            supported_language=supported_language,
            name=name or f"hf_ner_{model_name.split('/')[-1]}_{supported_language}",
        )

    def load(self) -> None:
        from transformers import pipeline

        self._pipeline = pipeline(
            "token-classification",
            model=self.model_name,
            aggregation_strategy="simple",
            device=self._device,
        )

    def analyze(
        self, text: str, entities: Iterable[str], nlp_artifacts: Optional[NlpArtifacts] = None
    ) -> list[RecognizerResult]:
        if self._pipeline is None:
            self.load()
        wanted = set(entities) if entities else set(self.supported_entities)
        results: list[RecognizerResult] = []
        for offset, chunk in _windows(text, self.window_chars, self.overlap_chars):
            for item in self._pipeline(chunk):  # type: ignore[misc]
                entity = self.entity_mapping.get(str(item["entity_group"]))
                if entity is None or entity not in wanted:
                    continue
                results.append(
                    RecognizerResult(
                        entity_type=entity,
                        start=offset + int(item["start"]),
                        end=offset + int(item["end"]),
                        score=float(item["score"]),
                        analysis_explanation=None,
                    )
                )
        return cap_structured(_dedupe(results), self.structured_score_cap)


def _windows(text: str, size: int, overlap: int) -> list[tuple[int, str]]:
    if len(text) <= size:
        return [(0, text)]
    out: list[tuple[int, str]] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        out.append((start, text[start:end]))
        if end == len(text):
            break
        start = end - overlap
    return out


def _dedupe(results: list[RecognizerResult]) -> list[RecognizerResult]:
    seen: dict[tuple[int, int, str], RecognizerResult] = {}
    for r in results:
        key = (r.start, r.end, r.entity_type)
        if key not in seen or seen[key].score < r.score:
            seen[key] = r
    return list(seen.values())
