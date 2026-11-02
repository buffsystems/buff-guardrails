"""The first (v1) extension of the shipped secret regexes, kept for comparison.
v2 won the #740 benchmark and ships as `buff_guardrails.passwords`.

v1 covers what the audit found missing: Russian key words ("пароль: …"), more
variable names (PASS, PW, AUTH, TOKEN, CRED), JSON keys and index syntax
(`"password": "…"`, `os.environ["X"] = "…"`, Go `:=`), CLI flags (`-p`, `-W`,
`--password`, `-u user:pass`) and values from 6 characters — with a looser
value than v2 (underscore, dash and dot count as signal, case-insensitive).
"""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer

from buff_guardrails.passwords import LATIN_NAME, RU_WORDS
from buff_guardrails.secrets import SECRET_CONTEXT

# v1 value: not a placeholder, carries a digit / upper / symbol (underscore and dash count)
VALUE = r"(?!\$\{|<|process\.env|os\.environ|changeme|xxx|\*\*\*|\{\{)(?=[^\s\"',;]*[\dA-Z!@#$%^&*_\-+=/.])[^\s\"',;)]{6,}"


def _base_patterns(value: str) -> list[Pattern]:
    return [
        # пароль: X / пароль X / пароль от вайфая X / Пароль от учётки — X
        Pattern("ru_keyword_value",
                rf"(?<=\b(?i:{RU_WORDS}(?:\s+(?:от|для|к|на)\s+[\w-]+)?)\s*[:=—–-]?\s*){value}", 0.65),
        # NAME=value / NAME: value / "name": "value" / env["NAME"] = "value" / name := "value"
        Pattern("named_value",
                rf"(?<=\b(?i:{LATIN_NAME})[\"'\]]{{0,2}}\s*(?:[:=]|:=|=>)\s*[\"'`]?){value}", 0.6),
        # CLI: -pVALUE, -p VALUE, -W VALUE, --password VALUE, --password=VALUE, --token VALUE
        Pattern("cli_flag_value",
                rf"(?<=\s(?:-p|-W|-P|(?i:--password|--passwd|--pass|--token|--secret|--api-key|--vault-password))[= ]?){value}", 0.6),
        Pattern("cli_glued_p", r"(?<=\s-p)(?![=\s-])[^\s\"',;]{6,}", 0.55),
        # -u user:pass / --user user:pass
        Pattern("cli_user_pass", r"(?<=\s(?:-u|--user)\s[^\s:]{1,40}:)[^\s\"']{4,}", 0.6),
        # htpasswd -b file user PASS / sshpass -p PASS already above
        Pattern("htpasswd_value", r"(?<=\bhtpasswd\s-b\s\S+\s\S+\s)\S{6,}", 0.6),
    ]


SECRET_EXT_PATTERNS = _base_patterns(VALUE)


def build_secret_ext_recognizer(language: str) -> PatternRecognizer:
    return PatternRecognizer(supported_entity="SECRET", name=f"buff_secret_ext_{language}", supported_language=language,
                             patterns=SECRET_EXT_PATTERNS, context=SECRET_CONTEXT)
