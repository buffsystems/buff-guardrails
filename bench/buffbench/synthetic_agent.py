"""Own `agent-runs` set: tool output as a coding agent sees it before it goes to
the model — a file it read, a command's stdout, a diff, a log tail, an API
response. Generated from a seed; each block carries 0–3 secrets among many
look-alikes (hashes, digests, UUIDs, request ids, versions, placeholders)."""

from __future__ import annotations

import random
import string

from .synthetic_secrets import _password, _pin, _token
from .types import Example, Span

HEX = "0123456789abcdef"


def _hex(rng: random.Random, n: int) -> str:
    return "".join(rng.choice(HEX) for _ in range(n))


def _uuid(rng: random.Random) -> str:
    return "-".join(_hex(rng, n) for n in (8, 4, 4, 4, 12))


# Blocks: `{pw}` / `{tok}` / `{pin}` are secrets, `{sha}` `{uuid}` `{ver}` `{host}` are visible noise.
BLOCKS = [
    "$ cat .env\nNODE_ENV=production\nPORT=3000\nDATABASE_URL=postgres://app:{pw}@db:5432/app\nREDIS_URL=redis://cache:6379/0\n"
    "SESSION_TTL=3600\nJWT_SECRET={tok}\nLOG_LEVEL=info\nBUILD_ID={sha}\n",
    "$ cat docker-compose.yml\nservices:\n  db:\n    image: postgres:16.2\n    environment:\n      - POSTGRES_USER=app\n"
    "      - POSTGRES_PASSWORD={pw}\n      - POSTGRES_DB=app\n  nats:\n    image: nats:2.10\n    command: --user app --pass {pw2}\n",
    "$ git diff\n--- a/config/settings.py\n+++ b/config/settings.py\n@@ -12,7 +12,7 @@\n DEBUG = False\n ALLOWED_HOSTS = ['{host}']\n"
    "-SMTP_PASSWORD = os.environ['SMTP_PASSWORD']\n+SMTP_PASSWORD = '{pw}'\n SMTP_PORT = 587\n",
    "$ tail -n 5 /var/log/app/api.log\n2026-10-30T12:01:02Z INFO request_id={uuid} GET /v1/items 200 12ms\n"
    "2026-10-30T12:01:03Z WARN request_id={uuid2} upstream slow 812ms\n"
    "2026-10-30T12:01:04Z DEBUG headers: Authorization: Bearer {tok} X-Trace: {sha}\n"
    "2026-10-30T12:01:05Z INFO request_id={uuid3} POST /v1/login 401\n",
    "$ kubectl get secret app-db -o yaml\napiVersion: v1\nkind: Secret\nmetadata:\n  name: app-db\n  uid: {uuid}\n"
    "type: Opaque\nstringData:\n  username: app\n  password: {pw}\n",
    "Traceback (most recent call last):\n  File \"db.py\", line 14, in connect\n    psycopg2.connect(\"host={host} user=app password={pw} dbname=app\")\n"
    "psycopg2.OperationalError: FATAL: password authentication failed for user \"app\"\n",
    "$ curl -s https://{host}/oauth/token -d grant_type=client_credentials\n{{\"access_token\": \"{tok}\", \"token_type\": \"Bearer\", "
    "\"expires_in\": 3600, \"request_id\": \"{uuid}\"}}\n",
    "$ docker images --digests | head -3\nREPOSITORY   TAG      DIGEST                                                                    IMAGE ID\n"
    "nginx        {ver}   sha256:{sha64}   {sha12}\npostgres     16.2     sha256:{sha64b}   {sha12b}\n",
    "$ git log --oneline -3\n{sha7} fix(auth): rotate signing key (#{num})\n{sha7b} chore(deps): bump requests to {ver}\n{sha7c} docs: deploy notes\n",
    "$ cat terraform.tfvars\nregion        = \"eu-central-1\"\ninstance_type = \"t3.medium\"\ndb_password   = \"{pw}\"\nvpc_id        = \"vpc-{sha8}\"\n",
    "$ env | grep -i -E 'pass|token|key'\nPGPASSWORD={pw}\nGITLAB_TOKEN={tok}\nSSH_AUTH_SOCK=/tmp/ssh-{sha8}/agent.{num}\nKEYBOARD_LAYOUT=us\n",
    "Пользователь: подключись к стенду, доступы: хост {host}, логин deploy, пароль {pw}, пин для VPN {pin}.\n"
    "Агент: подключаюсь по ssh deploy@{host}…\n",
    "Пользователь: тесты падают на CI, посмотри.\nАгент: в логе джоба #{num} вижу `database \"app\" does not exist`, "
    "коммит {sha7}; пароль в секретах CI не трогал. Пересоздаю базу.\n",
    "$ cat config.json\n{{\n  \"name\": \"api\",\n  \"version\": \"{ver}\",\n  \"db\": {{\"host\": \"{host}\", \"user\": \"app\", \"pass\": \"{pw}\"}},\n"
    "  \"features\": [\"push\", \"i18n\"],\n  \"build\": \"{sha}\"\n}}\n",
    "$ make test\npytest -q\n........................ 24 passed in 3.21s\ncoverage: 87%\nsession {uuid}\n",
    "$ ls -la ~/.ssh\n-rw------- 1 dev dev 2602 Oct 12 id_ed25519\n-rw-r--r-- 1 dev dev  569 Oct 12 id_ed25519.pub\n-rw-r--r-- 1 dev dev 1842 Oct 20 known_hosts\n",
]
SECRET_SLOTS = {"pw": _password, "pw2": _password, "tok": _token, "pin": _pin}


def generate_agent_runs(seed: int, count: int) -> list[Example]:
    rng = random.Random(seed)
    out: list[Example] = []
    for i in range(count):
        block = BLOCKS[i % len(BLOCKS)]
        noise = dict(
            sha=_hex(rng, 40), sha64=_hex(rng, 64), sha64b=_hex(rng, 64), sha12=_hex(rng, 12), sha12b=_hex(rng, 12),
            sha7=_hex(rng, 7), sha7b=_hex(rng, 7), sha7c=_hex(rng, 7), sha8=_hex(rng, 8), uuid=_uuid(rng),
            uuid2=_uuid(rng), uuid3=_uuid(rng), ver=f"{rng.randint(0, 9)}.{rng.randint(0, 20)}.{rng.randint(0, 50)}",
            host=rng.choice(["db.internal", "192.0.2.12", "stand.example.org", "api.example.com"]),
            num="".join(rng.choice(string.digits) for _ in range(rng.randint(2, 5))),
        )
        secrets = {k: f(rng) for k, f in SECRET_SLOTS.items() if "{" + k + "}" in block}
        text = block.format(**noise, **secrets)
        spans = []
        for value in secrets.values():
            start = text.find(value)
            while start >= 0:
                spans.append(Span(start, start + len(value), "SECRET"))
                start = text.find(value, start + 1)
        out.append(Example(text, spans, "ru" if "Пользователь" in text else "en", {"positive": bool(spans)}))
    return out
