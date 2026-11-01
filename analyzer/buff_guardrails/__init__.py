"""buff-guardrails: Presidio recognizers and engine wiring shared by the
analyzer image, the demo backend and the benchmark harness."""

from .engine import EngineSettings, build_analyzer
from .priority import without_overlaps

__all__ = ["EngineSettings", "build_analyzer", "without_overlaps"]
