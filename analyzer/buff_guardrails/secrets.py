"""Recognizers for secrets: provider API keys, private keys, JWTs, passwords.

Formats follow the public gitleaks rule set (prefixes and lengths), kept here
as plain regexes so they are easy to audit and extend.
"""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer

SECRET_ENTITY = "SECRET"

SECRET_PATTERNS = [
    Pattern("aws_access_key", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b", 0.9),
    Pattern("github_token", r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,255}\b", 0.9),
    Pattern("github_pat", r"\bgithub_pat_[A-Za-z0-9_]{82}\b", 0.9),
    Pattern("gitlab_pat", r"\bglpat-[A-Za-z0-9_-]{20,}\b", 0.9),
    Pattern("openai_key", r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b", 0.85),
    Pattern("anthropic_key", r"\bsk-ant-[A-Za-z0-9_-]{20,}\b", 0.95),
    Pattern("slack_token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b", 0.9),
    Pattern("google_api_key", r"\bAIza[0-9A-Za-z_-]{35}\b", 0.9),
    Pattern("stripe_key", r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{10,}\b", 0.9),
    Pattern("telegram_bot_token", r"\b\d{8,10}:[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-])", 0.85),
    Pattern("jwt", r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b", 0.9),
    Pattern(
        "private_key_block",
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-----",
        0.95,
    ),
    # Presidio matches with the `regex` module, so variable-length lookbehind is
    # fine: the match (what gets masked) is the secret value only.
    Pattern(
        "password_in_url",
        r"(?<=\b[a-z][a-z0-9+.-]*://[^\s:/@]+:)[^\s@/]{3,}(?=@)",
        0.85,
    ),
    Pattern(
        "assignment_secret",
        r"(?i)(?<=\b[a-z0-9_.-]*(?:api[_-]?key|secret|access[_-]?token|auth[_-]?token|password|passwd|pwd)[a-z0-9_]*\s*[:=]\s*[\"']?)[A-Za-z0-9_\-./+=!$%^&*#@]{8,}(?=[\"']?)",
        0.6,
    ),
    Pattern("bearer_header", r"(?i)(?<=\bbearer\s)[A-Za-z0-9_\-.=]{16,}(?![A-Za-z0-9_\-.=])", 0.7),
    Pattern("prefixed_token", r"\b(?:key|token|secret|tok|sk|pk|api)_[A-Za-z0-9]{16,}\b", 0.6),
    # Opaque strings (hex digests, long alphanumerics) are secrets only next to a
    # context word: "токен", "ключ", "пароль", "код" — a bare git SHA stays visible.
    Pattern("hex_blob", r"\b[0-9a-f]{32,64}\b", 0.1),
    Pattern("opaque_blob", r"(?<![\w/+=])[A-Za-z0-9_\-]{24,}(?![\w/+=])", 0.08),
]

SECRET_CONTEXT = ["token", "secret", "key", "ключ", "токен", "пароль", "password", "credential", "код", "api",
                  "авторизац", "верификац", "webhook", "доступ"]


def build_secret_recognizer(language: str) -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity=SECRET_ENTITY,
        name=f"buff_secret_{language}",
        supported_language=language,
        patterns=SECRET_PATTERNS,
        context=SECRET_CONTEXT,
    )
