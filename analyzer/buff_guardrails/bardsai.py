"""bardsai/password-detector as the judge of the secret cascade: a byte-level
CNN ensemble (default + large, int8 ONNX, 0.7 MB) with a tiny prefilter,
Apache-2.0, CPU only. Fetched into the Hugging Face cache on first start at a
pinned revision; its inference code ships inside the model repo."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = "bardsai/password-detector"
REVISION = "3e552ecd826970c888d99b56d0755ea926ff0b61"

Hit = tuple[int, int, float]


class BardsaiJudge:
    def __init__(self) -> None:
        self._det = None

    def load(self) -> None:
        from huggingface_hub import snapshot_download

        path = Path(snapshot_download(REPO, revision=REVISION))
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
        from password_detector.detector import SecretDetector

        onnx = path / "onnx"
        self._det = SecretDetector(
            f"{onnx / 'default' / 'model_int8.onnx'},{onnx / 'large' / 'model_int8.onnx'}",
            threshold=0.5,
            prefilter=str(onnx / "tiny" / "model_int8.onnx"),
        )

    def score_spans(self, text: str, spans: list[tuple[int, int]]) -> list[float]:
        """Probability that each (start, end) span of `text` is a secret, judged in context."""
        probs, _ = self._det.score_spans(text, spans)
        return [float(p) for p in probs]

    def scan(self, text: str) -> list[Hit]:
        return [(h["start"], h["end"], float(h["score"])) for h in self._det.scan(text)]
