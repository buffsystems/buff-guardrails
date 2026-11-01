"""Presidio recognizer backed by a GLiNER2-family model (gliner2 package).

Covers fastino/gliner2-* and hivetrace/gliner-guard-* checkpoints, which use
the GLiNER2 schema API rather than the classic `gliner` package that Presidio's
own GLiNERRecognizer wraps. Labels are requested in the model's taxonomy and
mapped to Presidio entities through `entity_mapping`.
"""

from __future__ import annotations

from typing import Iterable, Optional

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

from .priority import cap_structured


class Gliner2Recognizer(EntityRecognizer):
    def __init__(
        self,
        *,
        model_name: str,
        entity_mapping: dict[str, str],
        supported_language: str,
        threshold: float = 0.4,
        name: Optional[str] = None,
        structured_score_cap: float = 0.35,
    ) -> None:
        self.model_name = model_name
        self.structured_score_cap = structured_score_cap
        self.entity_mapping = entity_mapping
        self.threshold = threshold
        self._model = None
        self._schema = None
        super().__init__(
            supported_entities=sorted(set(entity_mapping.values())),
            supported_language=supported_language,
            name=name or f"gliner2_{model_name.split('/')[-1]}_{supported_language}",
        )

    def load(self) -> None:
        from gliner2 import GLiNER2

        self._model = GLiNER2.from_pretrained(self.model_name)
        self._schema = self._model.create_schema().entities(
            entity_types=list(self.entity_mapping), threshold=self.threshold
        )

    def analyze(
        self, text: str, entities: Iterable[str], nlp_artifacts: Optional[NlpArtifacts] = None
    ) -> list[RecognizerResult]:
        if self._model is None:
            self.load()
        wanted = set(entities) if entities else set(self.supported_entities)
        result = self._model.extract(  # type: ignore[union-attr]
            text, schema=self._schema, threshold=self.threshold, include_spans=True, include_confidence=True
        )
        out: list[RecognizerResult] = []
        for label, items in (result.get("entities") or {}).items():
            entity = self.entity_mapping.get(label)
            if entity is None or entity not in wanted:
                continue
            for item in items:
                start, end, score = _unpack(item)
                if start is None:
                    continue
                out.append(RecognizerResult(entity_type=entity, start=start, end=end, score=score))
        return cap_structured(out, self.structured_score_cap)


def _unpack(item: object) -> tuple[Optional[int], int, float]:
    """gliner2 returns dicts like {"text","start","end","confidence"}; be lenient."""
    if isinstance(item, dict):
        start, end = item.get("start"), item.get("end")
        if start is None and "span" in item:
            start, end = item["span"]
        score = float(item.get("confidence", item.get("score", 1.0)))
        return (int(start), int(end), score) if start is not None else (None, 0, 0.0)
    return (None, 0, 0.0)
