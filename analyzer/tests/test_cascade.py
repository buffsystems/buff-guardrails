"""The secret cascade (#740): confident regex hits and Russian-context hits pass,
weak regex candidates are judged by a model, the model's own scan is added
unless strict. Pure tests with an injected fake judge; one integration test
runs the real bardsai model when it is in the Hugging Face cache."""

import pytest

from buff_guardrails.cascade import CascadeSecretRecognizer
from buff_guardrails.engine import EngineSettings, secret_recognizers
from buff_guardrails.passwords import build_password_recognizer
from buff_guardrails.secrets import build_secret_recognizer


class FakeJudge:
    def __init__(self, prob=0.9, own=()):
        self.prob, self.own, self.scored, self.scanned = prob, list(own), [], 0

    def score_spans(self, text, spans):
        self.scored += [text[s:e] for s, e in spans]
        return [self.prob] * len(spans)

    def scan(self, text):
        self.scanned += 1
        return self.own


def cascade(judge, language="en", **kw):
    rules = [build_secret_recognizer(language), build_password_recognizer(language)]
    return CascadeSecretRecognizer(language, rules, judge, **kw)


def spans(recognizer, text):
    return {(text[r.start:r.end], round(r.score, 2)) for r in recognizer.analyze(text, ["SECRET"])}


def test_confident_regex_hits_pass_without_the_judge():
    judge = FakeJudge(prob=0.0)
    text = "key AKIAABCDEFGHIJKLMNOP and NATS_PASS=nats-s3cret-9"
    assert spans(cascade(judge), text) == {("AKIAABCDEFGHIJKLMNOP", 0.9), ("nats-s3cret-9", 0.85)}
    assert judge.scored == []


def test_weak_candidates_are_judged():
    text = 'token = "abcDEF123456"'
    assert spans(cascade(FakeJudge(prob=0.9)), text) == {("abcDEF123456", 0.9)}
    assert spans(cascade(FakeJudge(prob=0.49)), text) == set()
    judge = FakeJudge(prob=0.5)
    assert spans(cascade(judge), text) == {("abcDEF123456", 0.5)}
    assert judge.scored == ["abcDEF123456"]


def test_russian_key_word_and_context_are_trusted():
    judge = FakeJudge(prob=0.0)  # the model knows no Russian, so it must not get a vote
    assert ("Qwerty#2024", 0.85) in spans(cascade(judge, "ru"), "пароль: Qwerty#2024")
    blob = "6f5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c"
    assert (blob, 0.85) in spans(cascade(judge, "ru"), f"токен {blob}")
    assert judge.scored == []
    assert spans(cascade(judge, "en"), f"commit {blob}") == set()  # no context word: judged and rejected


def test_model_scan_is_added_unless_strict():
    text = "the value x9Kq2mP7vL4nR8sT appears"
    own = [(10, 26, 0.8)]
    assert spans(cascade(FakeJudge(own=own)), text) == {("x9Kq2mP7vL4nR8sT", 0.8)}
    strict = FakeJudge(own=own)
    assert spans(cascade(strict, own_scan=False), text) == set()
    assert strict.scanned == 0


def test_settings_secrets_mode_from_env():
    assert EngineSettings.from_env({}).secrets == "cascade"
    assert EngineSettings.from_env({"GUARDRAILS_SECRETS": "rules"}).secrets == "rules"
    with pytest.raises(ValueError):
        EngineSettings.from_env({"GUARDRAILS_SECRETS": "ml"})


def test_secret_recognizers_per_mode():
    names = lambda recs: [type(r).__name__ for r in recs]
    assert names(secret_recognizers("none", "en", None)) == ["PatternRecognizer"]
    assert names(secret_recognizers("rules", "en", None)) == ["PatternRecognizer", "PatternRecognizer"]
    assert names(secret_recognizers("cascade", "en", FakeJudge())) == ["CascadeSecretRecognizer"]
    strict = secret_recognizers("cascade-strict", "en", FakeJudge())
    assert names(strict) == ["CascadeSecretRecognizer"] and strict[0].own_scan is False
    # no judge (model unavailable): the regexes alone
    assert names(secret_recognizers("cascade", "en", None)) == ["PatternRecognizer", "PatternRecognizer"]


def test_judge_load_failure_falls_back_to_rules(monkeypatch, caplog):
    from buff_guardrails import bardsai
    from buff_guardrails.engine import load_judge

    def boom(self):
        raise OSError("no network")

    monkeypatch.setattr(bardsai.BardsaiJudge, "load", boom)
    assert load_judge(EngineSettings(secrets="cascade")) is None
    assert "regexes only" in caplog.text
    assert load_judge(EngineSettings(secrets="rules")) is None and bardsai  # rules never load a model


def test_real_model_when_cached():
    pytest.importorskip("onnxruntime")
    from buff_guardrails.bardsai import BardsaiJudge

    judge = BardsaiJudge()
    try:
        judge.load()
    except Exception as exc:  # no cache and no network
        pytest.skip(f"bardsai model unavailable: {exc}")
    text = 'db_password = "x9Kq2mP7vL4nR8sT"; mode = "production"'
    p_secret, p_word = judge.score_spans(text, [(15, 31), (42, 52)])
    assert p_secret > 0.5 > p_word
    assert any(text[s:e] == "x9Kq2mP7vL4nR8sT" for s, e, _ in judge.scan(text))
