"""HTTP server with the Presidio analyzer API, on top of the buff_guardrails engine.

Same contract as the official presidio-analyzer image (LiteLLM and the demo
talk to it): POST /analyze, GET /health, /recognizers, /supportedentities.
One addition: `language: "auto"` (the default) picks ru or en by script, so a
single LiteLLM guardrail covers mixed-language traffic.
"""

from __future__ import annotations

import logging
import os
import re

from flask import Flask, Response, jsonify, request

from buff_guardrails import EngineSettings, build_analyzer, without_overlaps

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("buff-guardrails")

CYRILLIC = re.compile(r"[А-Яа-яЁё]")
LATIN = re.compile(r"[A-Za-z]")


def detect_language(text: str, supported: list[str]) -> str:
    cyr, lat = len(CYRILLIC.findall(text)), len(LATIN.findall(text))
    if "ru" in supported and cyr >= lat * 0.3:
        return "ru"
    return "en" if "en" in supported else supported[0]


def create_app() -> Flask:
    settings = EngineSettings.from_env()
    analyzer = build_analyzer(settings)
    log.info("analyzer ready: languages=%s ner=%s gliner=%s hf=%s", settings.languages, settings.ner,
             settings.gliner_model, settings.hf_ner_model)
    app = Flask("buff-guardrails-analyzer")

    @app.get("/health")
    def health() -> Response:
        return Response("Presidio Analyzer service is up (buff-guardrails)", status=200)

    @app.post("/analyze")
    def analyze() -> Response:
        body = request.get_json(force=True, silent=True) or {}
        text = body.get("text")
        if not isinstance(text, str):
            return jsonify({"error": "text is required"}), 400
        language = body.get("language") or "auto"
        if language == "auto":
            language = detect_language(text, settings.languages)
        if language not in settings.languages:
            return jsonify({"error": f"unsupported language {language!r}, have {settings.languages}"}), 400
        results = analyzer.analyze(
            text=text,
            language=language,
            entities=body.get("entities"),
            score_threshold=body.get("score_threshold"),
            return_decision_process=bool(body.get("return_decision_process", False)),
        )
        return jsonify([r.to_dict() for r in without_overlaps(results)])

    @app.get("/recognizers")
    def recognizers() -> Response:
        language = request.args.get("language") or settings.languages[0]
        return jsonify([r.name for r in analyzer.get_recognizers(language)])

    @app.get("/supportedentities")
    def supported_entities() -> Response:
        language = request.args.get("language") or settings.languages[0]
        return jsonify(analyzer.get_supported_entities(language))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))
