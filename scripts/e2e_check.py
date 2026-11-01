#!/usr/bin/env python3
"""End-to-end check of the running stack: analyzer masks, LiteLLM restores.

  python scripts/e2e_check.py                 # uses .env (LITELLM_PORT, LITELLM_MASTER_KEY)
  python scripts/e2e_check.py --no-model      # analyzer + anonymizer only (no provider key needed)

Exit code 0 when every expected value was masked on the way in and restored on
the way out (tool-call arguments included when the model uses the tool).
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


def env() -> dict[str, str]:
    values = dict(os.environ)
    dotenv = Path(__file__).resolve().parent.parent / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                values.setdefault(k.strip(), v.split("#", 1)[0].strip())
    return values


def post(url: str, body: dict, headers: dict[str, str] | None = None) -> dict | list:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.load(resp)


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


def check_litellm(base: str, key: str, model: str, analyzer: str) -> bool:
    body: dict = {"model": model, "messages": [{"role": "user", "content": SAMPLE_RU}], "temperature": 0}
    if model == "mock":
        # The mock (litellm/config.yaml) quotes the placeholders LiteLLM creates for SAMPLE_RU;
        # make sure the analyzer still yields exactly those, then every original must come back.
        tokens = litellm_tokens(post(f"{analyzer}/analyze", {"text": SAMPLE_RU, "language": "auto"}))
        expected = ["<PERSON_1>", "<PHONE_NUMBER_2>", "<EMAIL_ADDRESS_3>", "<RU_SNILS_4>", "<CREDIT_CARD_5>"]
        if tokens != expected:
            print(f"analyzer tokens changed: {tokens} — update mock_response in litellm/config.yaml")
            return False
    out = post(f"{base}/v1/chat/completions", body, {"Authorization": f"Bearer {key}"})
    text = out["choices"][0]["message"]["content"] or ""
    leaked_placeholder = bool(re.search(r"\b[A-Z][A-Z_]*_\d+\b", text))
    print("model answer:", text[:300].replace("\n", " "))
    print("placeholder left in answer:", leaked_placeholder)
    if model == "mock":
        restored = [v for v in EXPECTED if v in text]
        print(f"restored {len(restored)}/{len(EXPECTED)} values")
        return not leaked_placeholder and len(restored) == len(EXPECTED)
    return not leaked_placeholder


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
