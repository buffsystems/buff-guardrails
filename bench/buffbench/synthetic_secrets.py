"""Own Russian + "agentic" secrets set, generated from a seed (`secrets-ru`).

Human passwords, PINs and tokens in the places a coding agent meets them:
Russian chat phrases, `.env`, docker-compose, JSON, source code, shell
commands. Negatives share the same frames: policy sentences, hashes,
versions, dates, placeholders, and the word "пароль" with no value after it.
"""

from __future__ import annotations

import random
import string

from .types import Example, Span

WORDS = ["Zima", "Solnyshko", "Barsik", "Moskva", "Leto", "Kotik", "Vesna", "Sever", "Raketa", "Volga",
         "Dacha", "Sosna", "Berkut", "Luna", "Ryabina", "Tigr", "Oblako", "Zvezda", "Reka", "Gora"]
SPECIAL = "!@#$%^&*_-"
HEX = "0123456789abcdef"
ALNUM = string.ascii_letters + string.digits


def _password(rng: random.Random) -> str:
    kind = rng.randrange(4)
    word = rng.choice(WORDS)
    if kind == 0:
        return f"{word}{rng.randint(1990, 2026)}{rng.choice(SPECIAL)}"
    if kind == 1:
        return f"{word.lower()}{rng.randint(10, 9999)}"
    if kind == 2:
        return "".join(rng.choice(ALNUM + SPECIAL) for _ in range(rng.randint(8, 14)))
    return f"{rng.choice(SPECIAL)}{word}_{rng.randint(1, 99)}"


def _token(rng: random.Random) -> str:
    return rng.choice([
        lambda: "".join(rng.choice(ALNUM) for _ in range(rng.randint(24, 40))),
        lambda: "".join(rng.choice(HEX) for _ in range(rng.choice([32, 40, 64]))),
        lambda: "ghp_" + "".join(rng.choice(ALNUM) for _ in range(36)),
        lambda: "sk-" + "".join(rng.choice(ALNUM) for _ in range(40)),
    ])()


def _pin(rng: random.Random) -> str:
    return "".join(rng.choice(string.digits) for _ in range(rng.choice([4, 6])))


# (frame, value kind). `{v}` is the secret; everything else is kept visible.
POSITIVE_FRAMES = [
    ("пароль: {v}", "pw"), ("пароль {v}", "pw"), ("пароль={v}", "pw"), ("Пароль от учётки — {v}", "pw"),
    ("логин admin пароль {v}", "pw"), ("вход: user admin, пароль {v}", "pw"), ("пароль от вайфая {v}", "pw"),
    ("пасс: {v}", "pw"), ("пароль для базы данных: {v}, логин тот же", "pw"),
    ("скинь пароль от стенда — {v}, только никому", "pw"), ("новый пароль {v}, старый больше не работает", "pw"),
    ("пин-код {v}", "pin"), ("пин: {v}", "pin"), ("код от домофона {v}", "pin"),
    ("токен: {v}", "tok"), ("ключ доступа {v}", "tok"), ("API ключ {v} не отвечает", "tok"),
    ("вот токен для стенда: {v}", "tok"), ("секрет вебхука: {v}", "tok"),
    ("DB_PASSWORD={v}", "pw"), ("SMTP_PASS={v}", "pw"), ("NATS_PASS={v}", "pw"), ("ADMIN_PW={v}", "pw"),
    ("REDIS_AUTH={v}", "pw"), ("export PGPASSWORD={v}", "pw"), ("MINIO_ROOT_PASSWORD={v}", "pw"),
    ("TOKEN={v}", "tok"), ("GITEA_TOKEN={v}", "tok"), ("JWT_SECRET={v}", "tok"),
    ("      - POSTGRES_PASSWORD={v}", "pw"), ("    password: {v}", "pw"), ("    POSTGRES_PASSWORD: {v}", "pw"),
    ('{{"password": "{v}"}}', "pw"), ('{{"db": {{"user": "app", "pass": "{v}"}}}}', "pw"),
    ('"apiKey": "{v}"', "tok"), ('{{"token": "{v}"}}', "tok"),
    ('password = "{v}"', "pw"), ("const dbPassword = '{v}';", "pw"), ('os.environ["DB_PASSWORD"] = "{v}"', "pw"),
    ("process.env.DB_PASSWORD = '{v}'", "pw"), ('secret := "{v}"', "pw"), ('auth = ("admin", "{v}")', "pw"),
    ('conn = psycopg2.connect(host="db", user="app", password="{v}")', "pw"),
    ("client = Client(api_key='{v}')", "tok"), ("Authorization: Bearer {v}", "tok"),
    ("DATABASE_URL=postgres://app:{v}@db:5432/app", "pw"),
    ("mysql -u root -p{v}", "pw"), ("sshpass -p {v} ssh root@host", "pw"), ("curl -u admin:{v} https://x/api", "pw"),
    ("docker login -u admin -p {v} registry", "pw"), ("psql -U app -W {v}", "pw"),
    ("htpasswd -b .htpasswd admin {v}", "pw"), ("ansible-vault --vault-password {v}", "pw"),
]

NEGATIVES = [
    "пароль должен содержать не менее 8 символов", "Пароль от учётки поменяли вчера, позвони мне",
    "пароль не подходит, сброси через админку", "забыл пароль, восстанови пожалуйста", "пин-код пришёл по смс",
    "токен протух, перевыпусти", "ключ от кабинета у охраны", "PASSWORD_MIN_LENGTH=8", "PASSWORD_RESET_TTL=3600",
    "DB_PASSWORD=${{DB_PASSWORD}}", "POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD}}", 'password: "<your-password>"',
    "SMTP_PASS=changeme", "TOKEN=", 'password = os.environ["DB_PASSWORD"]', "const token = process.env.TOKEN;",
    "версия {ver}, сборка {date}", "commit {sha} merged", "digest = sha256:{sha64}", "request_id={uuid}",
    "ETag: {sha}", "образ nginx:1.25.3 собран {date}", "заказ № {digits} оформлен", "ИНН 7707083893",
    "тел. +7 912 345-67-89", "см. тикет #{digits}", "ветка feature/{digits}-secrets", "pip install requests==2.31.0",
    "git checkout {sha}", "узел 192.0.2.1 недоступен", "{uuid}",
]


def _fill_negative(rng: random.Random, frame: str) -> str:
    return frame.format(
        ver=f"{rng.randint(0, 9)}.{rng.randint(0, 20)}.{rng.randint(0, 50)}",
        date=f"{rng.randint(1, 28):02d}.{rng.randint(1, 12):02d}.{rng.randint(2019, 2026)}",
        sha="".join(rng.choice(HEX) for _ in range(40)),
        sha64="".join(rng.choice(HEX) for _ in range(64)),
        uuid="-".join("".join(rng.choice(HEX) for _ in range(n)) for n in (8, 4, 4, 4, 12)),
        digits="".join(rng.choice(string.digits) for _ in range(rng.randint(3, 7))),
    )


def generate_secrets_ru(seed: int, count: int) -> list[Example]:
    rng = random.Random(seed)
    makers = {"pw": _password, "pin": _pin, "tok": _token}
    out: list[Example] = []
    for i in range(count):
        if i % 3 == 2:
            out.append(Example(_fill_negative(rng, NEGATIVES[i // 3 % len(NEGATIVES)]), [], "ru", {"positive": False}))
            continue
        frame, kind = POSITIVE_FRAMES[(i - i // 3) % len(POSITIVE_FRAMES)]
        value = makers[kind](rng)
        text = frame.format(v=value)
        start = text.index(value)
        out.append(Example(text, [Span(start, start + len(value), "SECRET")], "ru", {"positive": True, "kind": kind}))
    return out
