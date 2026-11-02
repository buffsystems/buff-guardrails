"""Presidio recognizers wrapping third-party secret detectors under test.

Each one returns SECRET spans with the tool's own confidence; nothing is
capped, so the bench sees the tool as shipped. Model files come from the
Hugging Face cache (`HF_HOME`), CredSweeper from the installed package.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, Optional

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

Hit = tuple[int, int, float]


def _snapshot(repo: str) -> Path:
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(repo))


def _limit_torch_threads(n: int = 4) -> None:
    """Torch defaults to one thread per core; on a shared host that oversubscribes
    (a 20 ms tagger took 1.4 s at 8 threads under load 11, 24 ms at 4)."""
    import torch

    torch.set_num_threads(min(n, torch.get_num_threads()))


class ExternalSecretRecognizer(EntityRecognizer):
    """Base: subclasses implement `_load` and `_scan(text) -> [(start, end, score)]`."""

    def __init__(self, supported_language: str, name: str) -> None:
        self._ready = False
        super().__init__(supported_entities=["SECRET"], supported_language=supported_language, name=name)

    def load(self) -> None:
        if not self._ready:
            self._load()
            self._ready = True

    def _load(self) -> None:
        raise NotImplementedError

    def _scan(self, text: str) -> list[Hit]:
        raise NotImplementedError

    def analyze(self, text: str, entities: Iterable[str], nlp_artifacts: Optional[NlpArtifacts] = None) -> list[RecognizerResult]:
        self.load()
        return [RecognizerResult("SECRET", s, e, score) for s, e, score in self._scan(text) if e > s]


class ChunkedRecognizer(EntityRecognizer):
    """Feed a recognizer line-aligned pieces of at most `max_chars`: GLiNER2 enumerates
    spans quadratically and took 26 GB (OOM) on 1500-char tool outputs."""

    def __init__(self, inner: EntityRecognizer, max_chars: int) -> None:
        self.inner, self.max_chars = inner, max_chars
        super().__init__(supported_entities=inner.supported_entities, supported_language=inner.supported_language,
                         name=f"chunked_{inner.name}")

    def load(self) -> None:
        self.inner.load()

    def analyze(self, text: str, entities: Iterable[str], nlp_artifacts: Optional[NlpArtifacts] = None) -> list[RecognizerResult]:
        out: list[RecognizerResult] = []
        for start, piece in _pieces(text, self.max_chars):
            for r in self.inner.analyze(piece, entities, nlp_artifacts):
                out.append(RecognizerResult(r.entity_type, r.start + start, r.end + start, r.score))
        return out


def _pieces(text: str, max_chars: int) -> list[tuple[int, str]]:
    pieces: list[tuple[int, str]] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            cut = text.rfind("\n", start, end)
            if cut > start:
                end = cut + 1
        pieces.append((start, text[start:end]))
        start = end
    return pieces


class CredSweeperRecognizer(ExternalSecretRecognizer):
    """Samsung CredSweeper: rules → candidates, BiLSTM validates (default `medium` threshold)."""

    def __init__(self, supported_language: str) -> None:
        super().__init__(supported_language, f"credsweeper_{supported_language}")

    def _load(self) -> None:
        from credsweeper.app import CredSweeper

        self._cs = CredSweeper(pool_count=1)

    def _scan(self, text: str) -> list[Hit]:
        from credsweeper.file_handler.string_content_provider import StringContentProvider

        lines = text.split("\n")
        offsets = [0]
        for line in lines[:-1]:
            offsets.append(offsets[-1] + len(line) + 1)
        self._cs.credential_manager.set_credentials(self._cs.file_scan(StringContentProvider(lines)))
        self._cs.post_processing(lambda *a, **k: None)
        hits: list[Hit] = []
        for cred in self._cs.credential_manager.get_credentials():
            for ld in cred.line_data_list:
                base = offsets[ld.line_num - 1]
                hits.append((base + ld.value_start, base + ld.value_end, float(cred.ml_probability or 1.0)))
        return hits


class CbxRecognizer(ExternalSecretRecognizer):
    """CobuildX cbx-secrets-detector (ModernBERT token tagger, 17M / 32M)."""

    def __init__(self, supported_language: str, repo: str = "CobuildX-AI/cbx-secrets-detector-32M") -> None:
        self.repo = repo
        super().__init__(supported_language, f"cbx_{repo.split('-')[-1]}_{supported_language}")

    def _load(self) -> None:
        path = _snapshot(self.repo)
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
        from cbx_secrets import SecretDetector  # ships inside the model repo

        _limit_torch_threads()
        self._det = SecretDetector(str(path), device="cpu")

    def _scan(self, text: str) -> list[Hit]:
        return [(s["start"], s["end"], 0.9) for s in self._det.extract(text)]


class BardsaiRecognizer(ExternalSecretRecognizer):
    """bardsai/password-detector: byte-level CNN cascade (tiny prefilter → default + large), int8 ONNX."""

    def __init__(self, supported_language: str, threshold: float = 0.5) -> None:
        self.threshold = threshold
        super().__init__(supported_language, f"bardsai_{supported_language}")

    def _load(self) -> None:
        path = _snapshot("bardsai/password-detector")
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
        from password_detector.detector import SecretDetector

        onnx = path / "onnx"
        self._det = SecretDetector(
            f"{onnx / 'default' / 'model_int8.onnx'},{onnx / 'large' / 'model_int8.onnx'}",
            threshold=self.threshold, prefilter=str(onnx / "tiny" / "model_int8.onnx"),
        )

    def _scan(self, text: str) -> list[Hit]:
        return [(h["start"], h["end"], float(h["score"])) for h in self._det.scan(text)]


class PrivacyFilterRecognizer(ExternalSecretRecognizer):
    """openai/privacy-filter (1.5B MoE token classifier); only its `secret` label is kept."""

    def __init__(self, supported_language: str) -> None:
        super().__init__(supported_language, f"privacy_filter_{supported_language}")

    def _load(self) -> None:
        import torch
        from transformers import pipeline

        _limit_torch_threads()
        self._clf = pipeline("token-classification", model="openai/privacy-filter", aggregation_strategy="simple",
                             device=-1, dtype=torch.bfloat16)

    def _scan(self, text: str) -> list[Hit]:
        return [(o["start"], o["end"], float(o["score"])) for o in self._clf(text) if o["entity_group"] == "secret"]
