"""Demo backend: masks text with the analyzer, optionally runs it through LiteLLM.

  POST /api/mask  {text, language?}          → masked text + entity list
  POST /api/run   {text, language?, task?}   → masked prompt, raw model answer, restored answer
  GET  /api/presets                          → demo preset sets (demo/presets.json)
  GET  /api/config                           → {model: bool, languages}

The "run" path masks here, sends the already-masked prompt through LiteLLM
(whose own guardrail then finds nothing left to hide) and restores the
placeholders in the answer — so every stage is visible in the UI.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests
from flask import Flask, jsonify, request, send_from_directory

from masking import mask, unmask

ANALYZER = os.environ.get("ANALYZER_URL", "http://analyzer:3000")
LITELLM = os.environ.get("LITELLM_URL", "http://litellm:4000")
LITELLM_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
LLM_CONFIGURED = bool(os.environ.get("LLM_MODEL"))
MODEL = os.environ.get("LITELLM_MODEL_NAME", "default")
MODEL_TIMEOUT = int(os.environ.get("MODEL_TIMEOUT", "600"))
MAX_TOKENS = int(os.environ.get("MODEL_MAX_TOKENS", "400"))
STATIC = Path(os.environ.get("STATIC_DIR", "/app/static"))
PRESETS = Path(os.environ.get("PRESETS_FILE", "/app/presets.json"))

app = Flask("buff-guardrails-demo", static_folder=None)


def analyze(text: str, language: str) -> list[dict]:
    resp = requests.post(f"{ANALYZER}/analyze", json={"text": text, "language": language}, timeout=120)
    resp.raise_for_status()
    return resp.json()


def masked_payload(text: str, language: str) -> dict:
    t0 = time.perf_counter()
    results = analyze(text, language)
    m = mask(text, results)
    return {
        "masked": m.text,
        "entities": [e.__dict__ for e in m.entities],
        "mapping": m.mapping,
        "analyzer_ms": round((time.perf_counter() - t0) * 1000),
    }


@app.post("/api/mask")
def api_mask():
    body = request.get_json(force=True) or {}
    text = body.get("text") or ""
    if not text.strip():
        return jsonify({"error": "empty text"}), 400
    return jsonify(masked_payload(text, body.get("language") or "auto"))


@app.post("/api/run")
def api_run():
    if not LLM_CONFIGURED:
        return jsonify({"error": "no model configured (LLM_MODEL is empty)"}), 409
    body = request.get_json(force=True) or {}
    text = body.get("text") or ""
    task = body.get("task") or ""
    if not text.strip():
        return jsonify({"error": "empty text"}), 400
    stage = masked_payload(text, body.get("language") or "auto")
    prompt = f"{task}\n\n{stage['masked']}" if task else stage["masked"]
    t0 = time.perf_counter()
    try:
        resp = requests.post(
            f"{LITELLM}/v1/chat/completions",
            headers={"Authorization": f"Bearer {LITELLM_KEY}"},
            json={"model": MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0,
                  "max_tokens": MAX_TOKENS},
            timeout=MODEL_TIMEOUT,
        )
    except requests.Timeout:
        return jsonify({"error": f"model did not answer within {MODEL_TIMEOUT}s (CPU inference is slow; try a smaller model)"}), 504
    if resp.status_code >= 400:
        return jsonify({"error": f"litellm {resp.status_code}: {resp.text[:400]}"}), 502
    raw = resp.json()["choices"][0]["message"]["content"] or ""
    stage.update(
        {
            "prompt": prompt,
            "raw_answer": raw,
            "answer": unmask(raw, stage["mapping"]),
            "model_ms": round((time.perf_counter() - t0) * 1000),
            "model": resp.json().get("model", MODEL),
        }
    )
    return jsonify(stage)


@app.get("/api/presets")
def api_presets():
    return jsonify(json.loads(PRESETS.read_text(encoding="utf-8")))


@app.get("/api/config")
def api_config():
    return jsonify({"model": LLM_CONFIGURED, "model_name": os.environ.get("LLM_MODEL", "")})


@app.get("/", defaults={"path": "index.html"})
@app.get("/<path:path>")
def static_files(path: str):
    target = STATIC / path
    if not target.is_file():
        path = "index.html"
    return send_from_directory(STATIC, path)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
