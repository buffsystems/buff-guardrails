"""Contextual password patterns (#740): the value after a key word, a variable
name, a CLI flag or inside a config element — in Russian and English — and the
private-key formats the provider list misses. Negatives are checked on the
recognizer alone, because the older generic `assignment_secret` rule still
flags some of them until the model judge (cascade) runs."""

import pytest

from buff_guardrails.engine import EngineSettings, build_analyzer
from buff_guardrails.passwords import build_password_recognizer

B58 = "1A2b3C4d5E6f7G8h9JkLmNpQrStUvWxYz"
XPRV = "xprv" + (B58 * 4)[:107]
AGE = "AGE-SECRET-KEY-1" + ("QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L" * 2)[:58]


@pytest.fixture(scope="module")
def analyzer():
    return build_analyzer(EngineSettings(ner="none", secrets="rules", spacy_models={"ru": "ru_core_news_sm", "en": "en_core_web_sm"}))


def secrets(analyzer, text, language):
    return {text[r.start:r.end] for r in analyzer.analyze(text=text, language=language) if r.entity_type == "SECRET"}


@pytest.mark.parametrize(
    "text, secret",
    [
        ("пароль: Qwerty#2024", "Qwerty#2024"),
        ("Пароль от вайфая — Tr0ub4dor&3, не раздавай", "Tr0ub4dor&3"),
        ("пин-код 4821-Ab", "4821-Ab"),
        ("ключ доступа к API: 7Yx9kQ2pLm", "7Yx9kQ2pLm"),
    ],
)
def test_russian_key_word_then_value(analyzer, text, secret):
    assert secret in secrets(analyzer, text, "ru")


@pytest.mark.parametrize(
    "text, secret",
    [
        ("NATS_PASS=nats-s3cret-9", "nats-s3cret-9"),
        ('os.environ["DB_PASSWORD"] = "pg-Adm1n-2024"', "pg-Adm1n-2024"),
        ('{"user": "app", "password": "Summ3r!2024"}', "Summ3r!2024"),
        ("smtp_pw := \"Ma1lBox#77\"", "Ma1lBox#77"),
        ("mysql -u root -pR00t#x7 shop", "R00t#x7"),
        ("psql --password=Pg$ecret9 -h db", "Pg$ecret9"),
        ("curl -u admin:Adm1n_2024 https://ci.local/job", "Adm1n_2024"),
        ("vault login -t 8f3a9c2e-1b4d-4e6f-9a8b-7c6d5e4f3a2b", "8f3a9c2e-1b4d-4e6f-9a8b-7c6d5e4f3a2b"),
        ('<key_store_password type="str">Ks#2024pass</key_store_password>', "Ks#2024pass"),
        ("<th>keystorepassword</th><td>Ks#2024x</td>", "Ks#2024x"),
    ],
)
def test_named_values_env_json_cli_xml(analyzer, text, secret):
    assert secret in secrets(analyzer, text, "en")


@pytest.mark.parametrize("text, secret", [(f"seed {XPRV} saved", XPRV), (f"key: {AGE}", AGE)])
def test_private_key_formats(analyzer, text, secret):
    assert secret in secrets(analyzer, text, "en")


@pytest.mark.parametrize(
    "text",
    [
        "token = self.access_token",  # a bare identifier has no digit, capital or symbol
        'password = os.environ.get("DB_PASSWORD")',  # a call, not a value
        "client_secret: your-client-secret",  # placeholder word
        "Authorization: Basic",  # keyword, not a value
        "DB_PASSWORD=${POSTGRES_PASSWORD}",  # shell substitution
        "password: changeme",
        "PASSWORD_MIN_LENGTH = 12",  # too short to be a password value
    ],
)
def test_recognizer_alone_ignores_placeholders_and_identifiers(text):
    recognizer = build_password_recognizer("en")
    assert recognizer.analyze(text, ["SECRET"]) == []


def test_recognizer_is_case_sensitive():
    recognizer = build_password_recognizer("en")
    # `access_token=` is not an env PASSWORD name; the lower-case value has no signal character
    assert recognizer.analyze("access_token=abcdefghij", ["SECRET"]) == []
    assert [r.score for r in recognizer.analyze("ACCESS_TOKEN=abcDEFghij", ["SECRET"])] == [0.85]
