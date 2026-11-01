"""Own synthetic sets, generated at load time from a seed (no PII stored).

`generate` — RU templates (chat, HR, banking, code, logs, contracts) with
Faker values and checksum-valid Russian identifiers, plus hard negatives.
`generate_secrets` — provider-key formats from the gitleaks rule set plus
look-alike negatives (hashes, UUIDs, versions, base64 without context).
"""

from __future__ import annotations

import random
import string

from faker import Faker

from .types import Example, Span

ALNUM = string.ascii_letters + string.digits


def _digits(rng: random.Random, n: int) -> str:
    return "".join(rng.choice(string.digits) for _ in range(n))


def luhn_complete(rng: random.Random, prefix: str, length: int) -> str:
    body = prefix + _digits(rng, length - len(prefix) - 1)
    total = 0
    for i, ch in enumerate(reversed(body)):
        v = int(ch)
        if i % 2 == 0:
            v = v * 2 if v * 2 <= 9 else v * 2 - 9
        total += v
    return body + str((10 - total % 10) % 10)


def snils(rng: random.Random) -> str:
    while True:
        number = _digits(rng, 9)
        if number < "001001998":
            continue
        total = sum(int(d) * (9 - i) for i, d in enumerate(number))
        control = total if total < 100 else (0 if total in (100, 101) else total % 101)
        control = 0 if control == 100 else control
        return f"{number[:3]}-{number[3:6]}-{number[6:]} {control:02d}"


def inn12(rng: random.Random) -> str:
    n = _digits(rng, 10)
    a = sum(int(d) * w for d, w in zip(n, (7, 2, 4, 10, 3, 5, 9, 4, 6, 8))) % 11 % 10
    b = sum(int(d) * w for d, w in zip(n + str(a), (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8))) % 11 % 10
    return n + str(a) + str(b)


def inn10(rng: random.Random) -> str:
    n = _digits(rng, 9)
    return n + str(sum(int(d) * w for d, w in zip(n, (2, 4, 10, 3, 5, 9, 4, 6, 8))) % 11 % 10)


def ogrn(rng: random.Random) -> str:
    n = "1" + _digits(rng, 11)
    return n + str(int(n) % 11 % 10)


def ru_phone(rng: random.Random) -> str:
    forms = ["+7 ({0}) {1}-{2}-{3}", "+7{0}{1}{2}{3}", "8 {0} {1} {2} {3}", "+7-{0}-{1}-{2}-{3}"]
    return rng.choice(forms).format(_digits(rng, 3), _digits(rng, 3), _digits(rng, 2), _digits(rng, 2))


def passport(rng: random.Random) -> str:
    return rng.choice(["{0} {1} {2}", "{0}{1} {2}", "{0} {1} № {2}"]).format(_digits(rng, 2), _digits(rng, 2), _digits(rng, 6))


# Each template: (language, text with {slots}, slot → (family, generator))
def _templates(ru: Faker, rng: random.Random):
    return [
        ("ru", "Здравствуйте! Меня зовут {p}, заказ №{order} не пришёл. Телефон {ph}, почта {em}.",
         {"p": ("PERSON", ru.name), "order": (None, lambda: _digits(rng, 7)), "ph": ("PHONE", lambda: ru_phone(rng)),
          "em": ("EMAIL", ru.email)}),
        ("ru", "Кандидат: {p}, дата рождения {dob}, паспорт {pp}, СНИЛС {sn}, ИНН {inn}. Адрес: {addr}.",
         {"p": ("PERSON", ru.name), "dob": ("DOB", lambda: ru.date_of_birth(minimum_age=18, maximum_age=65).strftime("%d.%m.%Y")),
          "pp": ("PASSPORT", lambda: passport(rng)), "sn": ("SNILS", lambda: snils(rng)), "inn": ("INN", lambda: inn12(rng)),
          "addr": ("ADDRESS", ru.address)}),
        ("ru", "Оплата картой {card}, CVC {cvc}, счёт {acc} в банке с БИК {bik}.",
         {"card": ("CARD", lambda: luhn_complete(rng, rng.choice(["4", "5", "2200"]), 16)), "cvc": ("CVC", lambda: _digits(rng, 3)),
          "acc": ("ACCOUNT", lambda: "40817810" + _digits(rng, 12)), "bik": ("BIK", lambda: "04" + _digits(rng, 7))}),
        ("ru", "ООО «{org}», ИНН {inn}, ОГРН {ogrn}, КПП {kpp}; директор {p}, тел. {ph}.",
         {"org": (None, ru.company), "inn": ("INN", lambda: inn10(rng)), "ogrn": ("OGRN", lambda: ogrn(rng)),
          "kpp": ("KPP", lambda: _digits(rng, 4) + "01" + _digits(rng, 3)), "p": ("PERSON", ru.name), "ph": ("PHONE", lambda: ru_phone(rng))}),
        ("ru", "Версия 2.14.3, сборка от {date}, коммит {sha}, задача {uuid}. Ошибок нет.",
         {"date": (None, lambda: ru.date(pattern="%d.%m.%Y")), "sha": (None, lambda: ru.sha1()[:12]), "uuid": (None, ru.uuid4)}),
        ("ru", "{p} написал: встретимся в {city} у метро, мой номер {ph}",
         {"p": ("PERSON", ru.name), "city": ("ADDRESS", ru.city), "ph": ("PHONE", lambda: ru_phone(rng))}),
        ("ru", "[{ts}] WARN auth: login failed for {em} from {ip}, user_id={uid}",
         {"ts": (None, lambda: ru.iso8601()), "em": ("EMAIL", ru.email), "ip": ("IP", ru.ipv4), "uid": (None, lambda: _digits(rng, 6))}),
        ("ru", "Договор № {contract} от {date}: Заказчик {p}, паспорт {pp}, проживающий по адресу {addr}.",
         {"contract": (None, lambda: f"{_digits(rng, 3)}/{_digits(rng, 2)}"), "date": (None, lambda: ru.date(pattern="%d.%m.%Y")),
          "p": ("PERSON", ru.name), "pp": ("PASSPORT", lambda: passport(rng)), "addr": ("ADDRESS", ru.address)}),
    ]


def _fill(language: str, template: str, slots: dict) -> Example:
    text = ""
    spans: list[Span] = []
    pos = 0
    pending_ip: tuple[int, int] | None = None
    for i, part in enumerate(template.split("{")):
        if i == 0:
            text += part
            continue
        key, rest = part.split("}", 1)
        family, gen = slots[key]
        value = str(gen())
        start = len(text)
        text += value
        if family == "IP_PART":  # 10.0.{a}.{b} — annotate the whole dotted address once
            if pending_ip is None:
                pending_ip = (text.rfind("10.0.", 0, start), len(text))
            else:
                spans.append(Span(pending_ip[0], len(text), "IP"))
                pending_ip = None
        elif family:
            spans.append(Span(start, len(text), family))
        text += rest
    return Example(text, spans, language, {"synthetic": True})


def generate(seed: int, count: int) -> list[Example]:
    rng = random.Random(seed)
    ru = Faker("ru_RU")
    Faker.seed(seed)
    templates = _templates(ru, rng)
    return [_fill(*templates[i % len(templates)]) for i in range(count)]


def _rand(rng: random.Random, alphabet: str, n: int) -> str:
    return "".join(rng.choice(alphabet) for _ in range(n))


def generate_secrets(seed: int, count: int) -> list[Example]:
    rng = random.Random(seed)
    makers = [
        lambda: "AKIA" + _rand(rng, string.ascii_uppercase + string.digits, 16),
        lambda: "ghp_" + _rand(rng, ALNUM, 36),
        lambda: "glpat-" + _rand(rng, ALNUM + "_-", 20),
        lambda: "sk-" + _rand(rng, ALNUM, 48),
        lambda: "sk-ant-api03-" + _rand(rng, ALNUM + "_-", 60),
        lambda: "xoxb-" + _digits(rng, 12) + "-" + _digits(rng, 12) + "-" + _rand(rng, ALNUM, 24),
        lambda: "AIza" + _rand(rng, ALNUM + "_-", 35),
        lambda: "sk_live_" + _rand(rng, ALNUM, 24),
        lambda: _digits(rng, 10) + ":" + _rand(rng, ALNUM + "_-", 35),
        lambda: "eyJ" + _rand(rng, ALNUM, 20) + "." + "eyJ" + _rand(rng, ALNUM, 40) + "." + _rand(rng, ALNUM + "_-", 43),
        lambda: "-----BEGIN RSA " + "PRIVATE KEY-----\n" + _rand(rng, ALNUM + "+/", 64) + "\n" + _rand(rng, ALNUM + "+/", 64) + "\n-----END RSA PRIVATE KEY-----",
    ]
    negatives = [
        lambda: _rand(rng, "0123456789abcdef", 40),  # git sha
        lambda: f"{_rand(rng, '0123456789abcdef', 8)}-{_rand(rng, '0123456789abcdef', 4)}-4{_rand(rng, '0123456789abcdef', 3)}-{_rand(rng, '0123456789abcdef', 4)}-{_rand(rng, '0123456789abcdef', 12)}",
        lambda: f"v{rng.randint(0, 9)}.{rng.randint(0, 20)}.{rng.randint(0, 50)}",
        lambda: _rand(rng, ALNUM + "+/", 44) + "=",  # bare base64 blob
        lambda: "sha256:" + _rand(rng, "0123456789abcdef", 64),
    ]
    frames = [
        ("export OPENAI_API_KEY={v}", "export BUILD_ID={v}"),
        ("Authorization: Bearer {v}", "ETag: {v}"),
        ("key = \"{v}\"", "digest = \"{v}\""),
        ("вот токен для стенда: {v}", "вот хеш сборки: {v}"),
        ("{v}", "{v}"),
    ]
    out: list[Example] = []
    for i in range(count):
        positive = i % 3 != 2
        frame = frames[i % len(frames)]
        value = (makers if positive else negatives)[i % (len(makers) if positive else len(negatives))]()
        template = frame[0] if positive else frame[1]
        start = template.index("{v}")
        text = template.replace("{v}", value)
        spans = [Span(start, start + len(value), "SECRET")] if positive else []
        out.append(Example(text, spans, "en", {"positive": positive}))
    return out
