# Подключение клиентов к шлюзу

Как направить Claude Code, Claude Desktop (включая Cowork), Buff Code (консоль и приложение)
и любой другой клиент через этот LiteLLM, чтобы персональные данные и секреты маскировались
до ухода в модель и восстанавливались в ответе.

## Что нужно знать заранее

После `docker compose up` шлюз отвечает на `http://<адрес>:4000` (порт `LITELLM_PORT` из `.env`).
Он говорит на двух языках API, поэтому подходит и OpenAI-клиентам, и клиентам Anthropic:

| API | Путь | Кто им пользуется |
|---|---|---|
| OpenAI Chat Completions | `/v1/chat/completions`, `/v1/models` | Buff Code, OpenAI SDK, большинство IDE-плагинов |
| Anthropic Messages | `/v1/messages`, `/v1/messages/count_tokens`, `/v1/models` | Claude Code, Claude Desktop и Cowork |

Guardrail включён для **всех** ключей (`default_on: true` в `litellm/config.yaml`): какой бы
клиент ни пришёл, запрос анализируется, сущности заменяются на `<PERSON_1>`, `<PHONE_NUMBER_2>` …,
а в ответе модели (в том числе в аргументах вызовов инструментов) заглушки заменяются обратно.
Стриминг работает, но ответ приходит одним куском в конце: LiteLLM буферизует поток, чтобы
восстановить значения.

**Имя модели.** В `litellm/config.yaml` описана одна рабочая модель с именем `default`
(провайдер и ключ берутся из `LLM_MODEL` / `LLM_API_KEY` / `LLM_API_BASE` в `.env`) и
служебная `mock` без провайдера. Клиенты, которые присылают собственные имена моделей
(Claude Code присылает `claude-…`), нужно либо научить просить `default`, либо добавить
алиасы в `config.yaml`:

```yaml
model_list:
  - model_name: default
    litellm_params: &provider
      model: os.environ/LLM_MODEL
      api_key: os.environ/LLM_API_KEY
      api_base: os.environ/LLM_API_BASE
  # алиасы под имена, которые просят клиенты по умолчанию
  - model_name: claude-sonnet-5-5
    litellm_params: *provider
  - model_name: claude-haiku-5-5
    litellm_params: *provider
```

После правки `config.yaml`: `docker compose restart litellm`.

**Ключ.** Для проверки годится `LITELLM_MASTER_KEY` из `.env`. Людям раздавайте не мастер-ключ,
а **виртуальные ключи**: откройте админку LiteLLM на том же адресе (`http://<адрес>:4000/ui`,
вход по мастер-ключу) → **Virtual Keys → Create Key**. Так расход считается по человеку, а
отзыв одного ключа ничего не ломает остальным. Ключи LiteLLM начинаются с `sk-`.

**Адрес.** На своей машине: `http://localhost:4000`. Для коллег по сети: адрес сервера, на
котором стоит compose, и открытый порт 4000 в файрволе; для доступа из интернета поставьте
перед шлюзом HTTPS (nginx, Caddy, Traefik) — клиенты Anthropic отказываются слать токен по
незащищённому редиректу, а Claude Desktop для удалённых SSH-сессий требует адрес, доступный
с удалённой машины, не `localhost`.

### Проверка шлюза до настройки клиентов

macOS / Linux (bash, zsh):

```sh
export GW=http://localhost:4000 KEY=sk-...
curl -sS "$GW/v1/models" -H "Authorization: Bearer $KEY"
curl -sS "$GW/v1/messages" -H "Authorization: Bearer $KEY" -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"default","max_tokens":50,"messages":[{"role":"user","content":"Меня зовут Иван Петров, тел. +7 912 345-67-89. Повтори, как меня зовут."}]}'
```

Windows (PowerShell):

```powershell
$GW = "http://localhost:4000"; $KEY = "sk-..."
Invoke-RestMethod "$GW/v1/models" -Headers @{ Authorization = "Bearer $KEY" }
Invoke-RestMethod -Method Post "$GW/v1/messages" `
  -Headers @{ Authorization = "Bearer $KEY"; "anthropic-version" = "2023-06-01" } `
  -ContentType "application/json" `
  -Body '{"model":"default","max_tokens":50,"messages":[{"role":"user","content":"Меня зовут Иван Петров, тел. +7 912 345-67-89. Повтори, как меня зовут."}]}'
```

Ответ начинается с `{"id":"msg_` и содержит исходное имя: модель видела `<PERSON_1>`, а вы
получили «Иван Петров» — демаскирование сработало. Что именно ушло в модель, видно в админке
LiteLLM (**Logs**) и в демо на `http://<адрес>:8080`. Полная проверка без провайдера:
`python scripts/e2e_check.py --model mock`.

## Claude Code

Claude Code читает адрес шлюза из `ANTHROPIC_BASE_URL`, ключ — из `ANTHROPIC_AUTH_TOKEN`
(уходит заголовком `Authorization: Bearer`, LiteLLM принимает именно его). Переменная с
ключом шлюза заменяет вход по подписке claude.ai: учёт идёт по токенам у владельца ключа
провайдера, а не по лимитам подписки.

### Шаг 1. Задать переменные

Сначала в текущем терминале, чтобы проверить; потом перенести в файл настроек.

macOS / Linux (bash, zsh):

```sh
export ANTHROPIC_BASE_URL=http://localhost:4000
export ANTHROPIC_AUTH_TOKEN=sk-...
export ANTHROPIC_MODEL=default
export ANTHROPIC_DEFAULT_SONNET_MODEL=default
export ANTHROPIC_DEFAULT_OPUS_MODEL=default
export ANTHROPIC_DEFAULT_HAIKU_MODEL=default
```

Windows (PowerShell):

```powershell
$env:ANTHROPIC_BASE_URL = "http://localhost:4000"
$env:ANTHROPIC_AUTH_TOKEN = "sk-..."
$env:ANTHROPIC_MODEL = "default"
$env:ANTHROPIC_DEFAULT_SONNET_MODEL = "default"
$env:ANTHROPIC_DEFAULT_OPUS_MODEL = "default"
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL = "default"
```

Windows (cmd):

```bat
set ANTHROPIC_BASE_URL=http://localhost:4000
set ANTHROPIC_AUTH_TOKEN=sk-...
set ANTHROPIC_MODEL=default
set ANTHROPIC_DEFAULT_SONNET_MODEL=default
set ANTHROPIC_DEFAULT_OPUS_MODEL=default
set ANTHROPIC_DEFAULT_HAIKU_MODEL=default
```

Четыре переменные с `MODEL` нужны потому, что Claude Code сам выбирает имена моделей
(`claude-…`) для основной работы и для фоновых задач; с ними все запросы идут в `default`.
Если вы добавили алиасы в `config.yaml` (см. выше), эти четыре строки можно не задавать.

Если на машине есть `ANTHROPIC_API_KEY` (ключ Anthropic), снимите его на время сессии
(`unset ANTHROPIC_API_KEY` / `Remove-Item Env:ANTHROPIC_API_KEY`): иначе Claude Code
отправит его вместо ключа шлюза и получит `401`.

### Шаг 2. Проверить

```sh
claude
```

Отправьте любое сообщение, затем выполните `/status`. На вкладке **Status** должны быть строки
`Anthropic base URL: http://localhost:4000` и `Auth token: ANTHROPIC_AUTH_TOKEN`. Если вместо
сессии открылся экран входа, переменные не дошли (см. шаг 3).

### Шаг 3. Закрепить в настройках

Чтобы переменные действовали во всех терминалах, редакторах и фоновых агентах, положите их в
блок `env` файла настроек Claude Code:

| ОС | Файл |
|---|---|
| macOS, Linux | `~/.claude/settings.json` |
| Windows | `%USERPROFILE%\.claude\settings.json` |

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:4000",
    "ANTHROPIC_AUTH_TOKEN": "sk-...",
    "ANTHROPIC_MODEL": "default",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "default",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "default",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "default"
  }
}
```

Не кладите ключ в `.claude/settings.json` внутри проекта: этот файл уходит в репозиторий.
Для одного проекта годится `.claude/settings.local.json` (добавьте его в `.gitignore`).
Значение из файла настроек имеет приоритет над переменной окружения.

Полезные дополнения в тот же блок `env`:

- `"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"` — отключает проверки обновлений,
  телеметрию и прочий трафик мимо шлюза (автообновление тоже выключится).
- `"CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1"` — если провайдер за шлюзом отвечает
  `400 … Extra inputs are not permitted` на экспериментальные поля запроса.
- `"CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": "1"` — добавить модели из `/v1/models`
  шлюза в список `/model`.

### Расширение VS Code

Расширение берёт переменные из собственных настроек VS Code, а не из `~/.claude/settings.json`.
**Preferences: Open User Settings (JSON)**:

```json
{
  "claudeCode.environmentVariables": [
    { "name": "ANTHROPIC_BASE_URL", "value": "http://localhost:4000" },
    { "name": "ANTHROPIC_AUTH_TOKEN", "value": "sk-..." },
    { "name": "ANTHROPIC_MODEL", "value": "default" },
    { "name": "ANTHROPIC_DEFAULT_SONNET_MODEL", "value": "default" },
    { "name": "ANTHROPIC_DEFAULT_OPUS_MODEL", "value": "default" },
    { "name": "ANTHROPIC_DEFAULT_HAIKU_MODEL", "value": "default" }
  ]
}
```

### Что меняется за шлюзом

- Remote Control и голосовой ввод недоступны: им нужна учётная запись claude.ai.
- Claude Code в Slack и облачные сессии через шлюз не ходят.
- Удалённые машины (SSH) настраиваются так же: переменные ставятся там, где запускается `claude`.

### Если не работает

| Симптом | Причина | Что сделать |
|---|---|---|
| `401` | Ключ не тот или ушёл не в тот заголовок | Проверьте ключ в админке LiteLLM; ключ должен быть в `ANTHROPIC_AUTH_TOKEN`, а `ANTHROPIC_API_KEY` снят |
| `Invalid model name passed in` | Клиент просит модель, которой нет в `config.yaml` | Задайте переменные `*_MODEL=default` или добавьте алиас |
| `400 … Extra inputs are not permitted` | Провайдер за шлюзом не знает экспериментальных полей | `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` |
| `400 … thinking … adaptive` | Модель за шлюзом не поддерживает adaptive thinking | Поменяйте `LLM_MODEL` на модель, которая поддерживает, или `CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING=1` |
| `Connection refused` | Шлюз не слушает на этом адресе | Проверьте `docker compose ps` и порт `LITELLM_PORT` |
| Просит войти, хотя curl работает | Нет ключа там, где Claude Code читает его до первого запуска | `ANTHROPIC_AUTH_TOKEN` в `~/.claude/settings.json` или в оболочке |
| Ответ приходит не по буквам, а целиком | Так работает демаскирование в стриминге | Это ожидаемо |

## Claude Desktop и Cowork

Claude Desktop (macOS и Windows; на Linux приложения нет, там Claude Code) не читает
`ANTHROPIC_BASE_URL`. Шлюз задаётся в его собственной конфигурации стороннего инференса, и
эта настройка общая для вкладок **Chat**, **Cowork** и **Code**: задачи Cowork ходят в модель
через тот же адрес и проходят тот же guardrail.

### На одной машине

1. **Help → Troubleshooting → Enable Developer Mode** (на Windows меню ☰ в левом верхнем углу
   экрана входа). Приложение перезапустится с меню **Developer**.
2. **Developer → Configure Third-Party Inference…**
3. В разделе **Connection**:
   - **Inference provider**: `Gateway`;
   - **Gateway base URL**: `http://localhost:4000` (без `/v1`);
   - **Gateway API key**: ваш `sk-…`;
   - **Gateway auth scheme**: `Bearer`.
4. В разделе **Models** перечислите модели. Автообнаружение через `/v1/models` показывает только
   имена, похожие на Claude, а у нас модель называется `default`, поэтому задайте список явно:
   имя `default`, а в поле `behavesAs` — идентификатор Claude, которому модель соответствует по
   возможностям (например `claude-sonnet-5-5`). Если вы добавили в `config.yaml` алиасы вида
   `claude-…`, список подхватится сам.
5. Нажмите **Test connection**, затем **Apply Changes**. Приложение перезапустится в режиме
   шлюза.

Окно сохраняет конфигурацию локально; при наличии управляемого профиля (MDM) оно открывается
только для чтения.

### На парк машин

В том же окне кнопка **Export** даёт готовые артефакты:

| Экспорт | Для чего |
|---|---|
| `.mobileconfig` | Jamf и любой macOS MDM |
| `.reg` | Intune, групповые политики, любой Windows MDM |
| JSON | конфигурационный файл для машины без MDM или ответ bootstrap-сервера |
| Firewall allowlist | список адресов для сетевой команды |

Ключи конфигурации: `inferenceProvider: "gateway"`, `inferenceGatewayBaseUrl`,
`inferenceGatewayApiKey`, `inferenceGatewayAuthScheme: "bearer"`, `inferenceModels`. Для
выдачи ключа по сотруднику вместо общего `inferenceGatewayApiKey` есть вход через ваш
IdP (`inferenceCredentialKind: "interactive"`), тогда LiteLLM проверяет JWT — это отдельная
настройка на стороне LiteLLM.

### Что меняется за шлюзом

- Недоступны облачные окружения Anthropic и Remote Control.
- Удалённые SSH-сессии Code требуют список хостов `sshHostAllowlist` и адрес шлюза, доступный с
  удалённой машины.
- LiteLLM сохраняет `cache_control` при передаче в Anthropic-совместимый провайдер; если
  провайдер другой, кеш промптов не работает, и каждый ход стоит полную цену входа.
- Экспериментальные бета-функции (tool search) на шлюзе выключены по умолчанию.

## Buff Code: консоль и приложение

Buff Code работает со своим провайдером без входа в Buff. LiteLLM подключается как
OpenAI-совместимый сервер блоком `provider` в конфигурации — одной и той же для терминального
интерфейса (`buff`) и для настольного приложения.

### Шаг 1. Файл конфигурации

| ОС | Файл |
|---|---|
| macOS, Linux | `~/.config/buff/buffcode.jsonc` |
| Windows | `%USERPROFILE%\.config\buff\buffcode.jsonc` |

Создайте файл, если его нет:

```jsonc
{
  "provider": {
    "litellm": {
      "name": "LiteLLM (guardrails)",
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "http://localhost:4000/v1",
        "apiKey": "{env:LITELLM_API_KEY}"
      },
      "models": {
        "default": { "name": "Модель организации через guardrails" }
      }
    }
  }
}
```

`{env:LITELLM_API_KEY}` подставит переменную окружения, `{file:~/.secrets/litellm}` прочитает
ключ из файла — так ключ не лежит в конфиге. Для одного проекта тот же блок можно положить в
`buffcode.json` в корне репозитория, но без ключа: файл уходит в git.

### Шаг 2. Ключ в окружение

macOS / Linux: `export LITELLM_API_KEY=sk-...` в `~/.zshrc` или `~/.bashrc`.
Windows (PowerShell, навсегда): `setx LITELLM_API_KEY "sk-..."`, затем новое окно терминала.
Настольное приложение, запущенное из Dock или меню «Пуск», переменные оболочки не видит — на
macOS/Linux вместо `{env:…}` используйте `{file:…}`, на Windows `setx` пишет переменную в
профиль пользователя, и приложение её увидит после перезапуска.

### Шаг 3. Выбрать модель

- Консоль: `buff models` показывает `litellm/default`; в сессии команда `/models`.
- Приложение: **Настройки → Провайдеры** — LiteLLM появится в списке; модель выбирается для
  каждой сессии.

Ходы на своей модели в журнал Buff не попадают и не списываются: учёт идёт только по ходам на
моделях организации.

## Другие клиенты

Любой OpenAI-совместимый клиент: `base_url = http://localhost:4000/v1`, `api_key = sk-…`,
`model = default`. Любой клиент Anthropic SDK: `base_url = http://localhost:4000`,
`auth_token = sk-…`. Guardrail один на все пути.

## Как убедиться, что маскирование работает

1. Демо `http://<адрес>:8080`: вставьте текст и посмотрите, что уйдёт в модель.
2. Админка LiteLLM → **Logs**: в сохранённых запросах вместо данных стоят заглушки.
3. `python scripts/e2e_check.py --model mock` — офлайн-проверка маскирования и восстановления.
4. В клиенте попросите модель повторить имя и телефон из вашего сообщения: в ответе они будут
   исходные, хотя модель видела `<PERSON_1>` и `<PHONE_NUMBER_2>`.
