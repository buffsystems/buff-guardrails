"""Secret-detector variants: the shipped regexes, the extended regexes, and
third-party models alone or on top of the regexes (`rules+…`).

Every variant restricts the analyzer to SECRET, so other recognizers do not
run; `without_secret_rules` drops the shipped regexes to see a model alone."""

from __future__ import annotations

from buff_guardrails.engine import EngineSettings
from buff_guardrails.gliner2_ner import Gliner2Recognizer
from buff_guardrails.passwords import build_password_recognizer

from .detectors import Detector
from .secret_cascade import CascadeRecognizer, UnionRecognizer
from .secret_recognizers import (BardsaiRecognizer, CbxRecognizer, ChunkedRecognizer, CredSweeperRecognizer,
                                 PrivacyFilterRecognizer)
from .secret_rules_ext import build_secret_ext_recognizer

# Secret variants build the regex layer explicitly; `product-*` run the shipped engine as configured.
RULES = EngineSettings(ner="none", secrets="rules")
GUARDRAILS_SECRET_LABELS = {k: "SECRET" for k in ("password", "secret", "api_key", "access_token", "recovery_code")}
GLINER2_GUARDRAILS = "fastino/GLiNER2-Guardrails-PII-Multi"


def _gliner2_guardrails(lang: str) -> ChunkedRecognizer:
    inner = Gliner2Recognizer(model_name=GLINER2_GUARDRAILS, entity_mapping=GUARDRAILS_SECRET_LABELS,
                              supported_language=lang, threshold=0.4, structured_score_cap=1.0)
    return ChunkedRecognizer(inner, max_chars=600)


def _privacy_filter(lang: str) -> ChunkedRecognizer:
    return ChunkedRecognizer(PrivacyFilterRecognizer(lang), max_chars=1500)


def _both(a, b):
    """Two extra recognizers on one detector (regex extension + a model)."""
    return lambda lang: [a(lang), b(lang)]


def _variants(name: str, description: str, extra) -> dict[str, Detector]:
    """`<name>` = model alone, `rules+<name>` = model on top of the shipped regexes."""
    return {
        name: Detector(name, description, RULES, extra, ["SECRET"], without_secret_rules=True),
        f"rules+{name}": Detector(f"rules+{name}", f"shipped regexes + {description}", RULES,
                                  extra, ["SECRET"]),
    }


SECRET_DETECTORS: dict[str, Detector] = {
    # Since #740 the shipped regexes include the password patterns v2 (`rules-ext2` before the move).
    "rules-secret": Detector("rules-secret", "shipped secret regexes only (provider formats + password patterns v2)",
                             RULES, None, ["SECRET"]),
    "rules-ext": Detector("rules-ext", "shipped + extended regexes (RU key words, JSON/env/CLI, 6+ chars)",
                          RULES, build_secret_ext_recognizer, ["SECRET"]),
    **_variants("credsweeper", "Samsung CredSweeper 1.19 (rules + BiLSTM, CPU)", CredSweeperRecognizer),
    **_variants("cbx-32m", "CobuildX cbx-secrets-detector-32M (ModernBERT tagger)", CbxRecognizer),
    **_variants("cbx-17m", "CobuildX cbx-secrets-detector-17M",
                lambda lang: CbxRecognizer(lang, "CobuildX-AI/cbx-secrets-detector-17M")),
    **_variants("bardsai", "bardsai/password-detector cascade (byte CNN, 0.7 MB int8 ONNX)", BardsaiRecognizer),
    **_variants("gliner2-guardrails", "fastino/GLiNER2-Guardrails-PII-Multi secret labels (0.3B)", _gliner2_guardrails),
    **_variants("privacy-filter", "openai/privacy-filter `secret` label (1.5B MoE, bf16 CPU)", _privacy_filter),
    "rules-ext+bardsai": Detector("rules-ext+bardsai", "extended regexes + bardsai cascade", RULES,
                                  _both(build_secret_ext_recognizer, BardsaiRecognizer), ["SECRET"]),
    "rules-ext+cbx-32m": Detector("rules-ext+cbx-32m", "extended regexes + cbx-32M", RULES,
                                  _both(build_secret_ext_recognizer, CbxRecognizer), ["SECRET"]),
}


def _alone(name: str, description: str, make) -> Detector:
    """A cascade / ensemble recognizer replaces the shipped regexes entirely (it runs them itself)."""
    return Detector(name, description, RULES, make, ["SECRET"], without_secret_rules=True)


SECRET_DETECTORS.update({
    "cascade-bardsai": _alone("cascade-bardsai", "confident regexes + weak regex candidates judged by bardsai (p≥0.3) + bardsai scan",
                              lambda l: CascadeRecognizer(l, name="cascade_bardsai")),
    "cascade-bardsai-judge": _alone("cascade-bardsai-judge", "confident regexes + weak candidates judged by bardsai, no own scan",
                                    lambda l: CascadeRecognizer(l, own_scan=False, name="cascade_bardsai_judge")),
    "cascade-bardsai-t0.5": _alone("cascade-bardsai-t0.5", "cascade-bardsai with judge threshold 0.5",
                                   lambda l: CascadeRecognizer(l, judge_threshold=0.5, name="cascade_bardsai_t05")),
    "cascade-bardsai-noext": _alone("cascade-bardsai-noext", "cascade-bardsai over the shipped regexes only (no extension)",
                                    lambda l: CascadeRecognizer(l, ext=False, name="cascade_bardsai_noext")),
    "cascade-bardsai-notrust": _alone("cascade-bardsai-notrust", "cascade-bardsai with the Russian key-word pattern judged too",
                                      lambda l: CascadeRecognizer(l, trust=(), name="cascade_bardsai_notrust")),
    "cascade-cbx": _alone("cascade-cbx", "confident regexes + weak candidates confirmed by cbx-32M overlap + cbx scan",
                          lambda l: CascadeRecognizer(l, judges=("cbx",), name="cascade_cbx")),
    "cascade-bardsai+cbx": _alone("cascade-bardsai+cbx", "confident regexes + weak candidates judged by bardsai or cbx + both scans",
                                  lambda l: CascadeRecognizer(l, judges=("bardsai", "cbx"), name="cascade_both")),
    "cascade2-bardsai": _alone("cascade2-bardsai", "cascade over the shipped regexes (password patterns v2), judge bardsai p≥0.5",
                               lambda l: CascadeRecognizer(l, judge_threshold=0.5, ext_builder=build_password_recognizer,
                                                           name="cascade2_bardsai")),
    "product-cascade": Detector("product-cascade", "the shipped analyzer, GUARDRAILS_SECRETS=cascade",
                                EngineSettings(ner="none", secrets="cascade"), None, ["SECRET"]),
    "product-cascade-strict": Detector("product-cascade-strict", "the shipped analyzer, GUARDRAILS_SECRETS=cascade-strict",
                                       EngineSettings(ner="none", secrets="cascade-strict"), None, ["SECRET"]),
    "bardsai+cbx": _alone("bardsai+cbx", "union of bardsai and cbx-32M, no regexes", lambda l: UnionRecognizer(l)),
    "bardsai-t0.3": _alone("bardsai-t0.3", "bardsai cascade at threshold 0.3", lambda l: BardsaiRecognizer(l, threshold=0.3)),
    "bardsai-t0.7": _alone("bardsai-t0.7", "bardsai cascade at threshold 0.7", lambda l: BardsaiRecognizer(l, threshold=0.7)),
})
