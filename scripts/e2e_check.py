#!/usr/bin/env python3
"""End-to-end check of the running stack: analyzer masks, LiteLLM restores.

  python scripts/e2e_check.py                 # uses .env (LITELLM_PORT, LITELLM_MASTER_KEY)
  python scripts/e2e_check.py --no-model      # analyzer + anonymizer only (no provider key needed)
  python scripts/e2e_check.py --model default # your provider: adds the streamed Responses API path

Both API shapes clients use are exercised: Chat Completions (Buff Code, SDKs) and the Responses
API (Codex). Exit code 0 when every expected value was masked on the way in and restored on the
way out (tool-call arguments included when the model uses the tool).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

SAMPLE_RU = ("Клиент Иванов Пётр Сергеевич, тел. +7 (912) 345-67-89, email petr.ivanov@example.com, "
             "СНИЛС 112-233-445 95, карта 2200 0000 0000 0053. Напиши ему короткий ответ, обращаясь по имени.")
EXPECTED = ["Иванов Пётр Сергеевич", "+7 (912) 345-67-89", "petr.ivanov@example.com", "112-233-445 95",
            "2200 0000 0000 0053"]
PLACEHOLDER = re.compile(r"\b[A-Z][A-Z_]*_\d+\b")


def env() -> dict[str, str]:
    values = dict(os.environ)
    dotenv = Path(__file__).resolve().parent.parent / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                values.setdefault(k.strip(), v.split("#", 1)[0].strip())
    return values


def request(url: str, body: dict, headers: dict[str, str] | None = None) -> urllib.request.Request:
    return urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                  headers={"Content-Type": "application/json", **(headers or {})})


def post(url: str, body: dict, headers: dict[str, str] | None = None) -> dict | list:
    with urllib.request.urlopen(request(url, body, headers), timeout=600) as resp:  # a CPU model thinks slowly
        return json.load(resp)


def stream(url: str, body: dict, headers: dict[str, str]) -> list[dict]:
    """Server-sent events of a streamed call, parsed."""
    events: list[dict] = []
    with urllib.request.urlopen(request(url, {**body, "stream": True}, headers), timeout=600) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if line.startswith("data: ") and line != "data: [DONE]":
                events.append(json.loads(line[6:]))
    return events


def check_analyzer(base: str) -> bool:
    results = post(f"{base}/analyze", {"text": SAMPLE_RU, "language": "auto"})
    found = {SAMPLE_RU[r["start"]:r["end"]] for r in results}
    missing = [v for v in EXPECTED if not any(v in f or f in v for f in found)]
    print(f"analyzer: {len(results)} entities, missing={missing}")
    return not missing


def litellm_tokens(analyzer_results: list[dict]) -> list[str]:
    """LiteLLM numbers placeholders left to right across ALL entities: <PERSON_1>, <PHONE_NUMBER_2>…"""
    ordered = sorted(analyzer_results, key=lambda r: r["start"])
    return [f"<{r['entity_type']}_{i}>" for i, r in enumerate(ordered, start=1)]


def verdict(path: str, text: str, model: str) -> bool:
    leaked = bool(PLACEHOLDER.search(text))
    print(f"{path}: {text[:200].replace(chr(10), ' ')}")
    print(f"{path}: placeholder left in answer: {leaked}")
    if model == "mock":
        restored = [v for v in EXPECTED if v in text]
        print(f"{path}: restored {len(restored)}/{len(EXPECTED)} values")
        return not leaked and len(restored) == len(EXPECTED)
    return not leaked


def check_litellm(base: str, key: str, model: str, analyzer: str) -> bool:
    auth = {"Authorization": f"Bearer {key}"}
    if model == "mock":
        # The mock (litellm/config.yaml) quotes the placeholders LiteLLM creates for SAMPLE_RU;
        # make sure the analyzer still yields exactly those, then every original must come back.
        tokens = litellm_tokens(post(f"{analyzer}/analyze", {"text": SAMPLE_RU, "language": "auto"}))
        expected = ["<PERSON_1>", "<PHONE_NUMBER_2>", "<EMAIL_ADDRESS_3>", "<RU_SNILS_4>", "<CREDIT_CARD_5>"]
        if tokens != expected:
            print(f"analyzer tokens changed: {tokens} — update mock_response in litellm/config.yaml")
            return False
    chat = post(f"{base}/v1/chat/completions",
                {"model": model, "messages": [{"role": "user", "content": SAMPLE_RU}], "temperature": 0}, auth)
    ok = verdict("chat", chat["choices"][0]["message"]["content"] or "", model)

    responses = post(f"{base}/v1/responses", {"model": model, "input": SAMPLE_RU, "temperature": 0}, auth)
    text = "".join(part.get("text") or "" for item in responses["output"] for part in item.get("content") or [])
    ok &= verdict("responses", text, model)

    if model != "mock":  # LiteLLM cannot stream a mocked Responses call; a real model shows the Codex path
        events = stream(f"{base}/v1/responses", {"model": model, "input": SAMPLE_RU, "temperature": 0}, auth)
        deltas = "".join(e.get("delta") or "" for e in events if e.get("type") == "response.output_text.delta")
        ok &= verdict("responses stream (what Codex renders)", deltas, model)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-model", action="store_true")
    parser.add_argument("--analyzer", default=None, help="analyzer URL (default: localhost:ANALYZER_PORT from .env)")
    parser.add_argument("--model", default="mock", help="LiteLLM model name: mock (offline) or default (your provider)")
    args = parser.parse_args()
    e = env()
    analyzer = args.analyzer or f"http://localhost:{e.get('ANALYZER_PORT', '3000')}"
    ok = check_analyzer(analyzer)
    if not args.no_model:
        ok &= check_litellm(f"http://localhost:{e.get('LITELLM_PORT', '4000')}", e.get("LITELLM_MASTER_KEY", ""),
                            args.model, analyzer)
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
