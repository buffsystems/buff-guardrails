"""Passwords and keys that have no fixed format: the value is recognised by
what stands before it — a Russian or English key word, a variable name, a
CLI flag, a config element — plus the private-key formats the provider list
in `secrets.py` misses (BIP32, WIF, age). Chosen by the #740 benchmark.

Only the value is matched, so only the value is masked. A value must carry a
digit, a capital letter or a symbol (an identifier such as `self.access_token`
has none), must not be a placeholder word or call syntax, and the patterns
are compiled case-sensitively: Presidio's default IGNORECASE would make
`[A-Z]` match any letter and `NAME_PASSWORD=` match `access_token=`."""

from __future__ import annotations

import regex
from presidio_analyzer import Pattern, PatternRecognizer

from .secrets import SECRET_CONTEXT, SECRET_ENTITY

RU_WORDS = r"(?:парол[ьяюе]м?|пасс(?:ворд)?|пин(?:-?код)?|кодовое слово|секрет|токен|ключ(?: доступа)?|код)"
LATIN_NAME = r"[A-Za-z0-9_.\-]*(?:pass|pwd|pw|secret|token|auth|cred|key|pin)[A-Za-z0-9_.\-]*"
ENV_NAME = r"[A-Z][A-Z0-9_]*(?:PASS|PASSWORD|PASSWD|PWD|SECRET|TOKEN|API_KEY|ACCESS_KEY|PRIVATE_KEY|CRED)[A-Z0-9_]*"
B58 = "[1-9A-HJ-NP-Za-km-z]"

PLACEHOLDER = r"(?![^\s\"',;<>()\[\]{}]*(?i:secret|passw|example|dummy|placeholder|changeme|insecure|sample|your[-_]|xxx))"
KEYWORDS = r"(?!(?i:bearer|basic|optional|none|null|true|false|param|string|digest)\b)"
VALUE = (
    rf"(?!\$\{{|\$[A-Z]|<|\{{\{{|\*\*\*){PLACEHOLDER}{KEYWORDS}(?![a-z_][a-z0-9_.]*[(\[])"
    rf"(?=[^\s\"',;<>()\[\]{{}}]*[\dA-Z!@#$%^&*+=])[^\s\"',;()\[\]{{}}<>]{{6,}}(?![\[(])"
)

# Weak (0.55–0.65): a model judge decides in the cascade. Confident (0.85+): kept as is.
PASSWORD_PATTERNS = [
    # пароль: X / пароль от вайфая — X / токен доступа к API: X
    Pattern("ru_keyword_value", rf"(?<=\b(?i:{RU_WORDS}(?:\s+(?:от|для|к|на)\s+[\w-]+)?)\s*[:=—–-]?\s*){VALUE}", 0.65),
    # NAME=value / name: value / "name": "value" / env["NAME"] = "value" / name := "value"
    Pattern("named_value", rf"(?<=\b(?i:{LATIN_NAME})[\"'\]]{{0,2}}\s*(?:[:=]|:=|=>)\s*[\"'`]?){VALUE}", 0.6),
    # -p VALUE, -W VALUE, --password VALUE, --password=VALUE, --token VALUE
    Pattern("cli_flag_value",
            rf"(?<=\s(?:-p|-W|-P|(?i:--password|--passwd|--pass|--token|--secret|--api-key|--vault-password))[= ]?){VALUE}",
            0.6),
    Pattern("cli_glued_p", r"(?<=\s-p)(?![=\s-])[^\s\"',;]{6,}", 0.55),
    Pattern("cli_user_pass", r"(?<=\s(?:-u|--user)\s[^\s:]{1,40}:)[^\s\"']{4,}", 0.6),
    Pattern("htpasswd_value", r"(?<=\bhtpasswd\s-b\s\S+\s\S+\s)\S{6,}", 0.6),
    Pattern("env_assignment", rf"(?<=\b{ENV_NAME}\s*[=:]\s*[\"']?)(?=.{{8,}}){VALUE}", 0.85),
    Pattern("password_named_value",
            rf"(?<=\b(?i:[a-z0-9_.\-]*(?:password|passwd|pwd)[a-z0-9_.\-]*)[\"'\]]{{0,2}}\s*(?:[:=]|=>)\s*[\"'`]?){VALUE}",
            0.85),
    Pattern("xml_password_element", rf"(?<=<(?i:[a-z0-9_\-]*password[^>]*)>){VALUE}(?=</)", 0.85),
    Pattern("html_password_cell", rf"(?<=(?i:<th>[^<]*password[^<]*</th>)\s*<td>){VALUE}(?=</td>)", 0.85),
    Pattern("bip32_private_key", rf"\b[xt]prv{B58}{{107,108}}\b", 0.95),
    Pattern("wif_private_key", rf"(?<=[\"'\s])(?:5[HJK]{B58}{{49}}|[KLc]{B58}{{51}})(?=[\"'\s,)])", 0.85),
    Pattern("age_secret_key", r"\bAGE-SECRET-KEY-1[0-9A-Z]{58}\b", 0.95),
    Pattern("cli_t_token", r"(?<=\s-t\s)(?=[^\s]*\d)[A-Za-z0-9-]{20,}", 0.85),
]


def build_password_recognizer(language: str) -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity=SECRET_ENTITY,
        name=f"buff_secret_passwords_{language}",
        supported_language=language,
        patterns=PASSWORD_PATTERNS,
        context=SECRET_CONTEXT,
        global_regex_flags=regex.DOTALL | regex.MULTILINE,
    )
