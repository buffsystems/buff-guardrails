#!/usr/bin/env bash
# buff-guardrails — установка / install.
#
# Спрашивает цифрами, какой сетап нужен, пишет .env и поднимает docker compose. Всё работает
# внутри вашего периметра: модель — локальная (Ollama, vLLM) или ваш собственный сервер;
# никаких внешних провайдеров. Повторный запуск — норма: ключи и пароли сохраняются.
# Asks (by number) which setup you want, writes .env and starts docker compose. Everything
# stays inside your perimeter: the model is local (Ollama, vLLM) or your own server; no
# external providers. Re-running is fine: keys and passwords are kept.
#
#   ./install.sh                 интерактивно / interactive
#   ./install.sh --lang en       язык подсказок / prompt language
#   ./install.sh --yes           без вопросов: spaCy, пароли правилами + моделью, без LLM / defaults, no LLM
#
# Windows: run from Git Bash or WSL with Docker Desktop started.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

LANG_CHOICE="${BUFF_LANG:-}"; YES=0
for a in "$@"; do case "$a" in --lang=*) LANG_CHOICE="${a#--lang=}" ;; --lang) ;; en|ru) LANG_CHOICE="$a" ;; --yes|-y) YES=1 ;; esac; done
if [ "$LANG_CHOICE" != en ] && [ "$LANG_CHOICE" != ru ]; then
  LANG_CHOICE=ru
  langs="${LANGUAGE:-}"; for tag in ${langs//:/ } ${LC_ALL:-} ${LC_MESSAGES:-} ${LANG:-}; do
    case "${tag%%[_.@-]*}" in ru) break ;; en) LANG_CHOICE=en; break ;; esac
  done
fi
t() { if [ "$LANG_CHOICE" = en ] && [ -n "${2:-}" ]; then printf '%s' "$2"; else printf '%s' "$1"; fi; }
say() { printf '\033[1m[guardrails]\033[0m %s\n' "$(t "$@")"; }
die() { printf '\033[1;31m[guardrails]\033[0m %s\n' "$(t "$@")" >&2; exit 1; }

# ---- prerequisites -------------------------------------------------------------------------
command -v docker >/dev/null 2>&1 || die "нужен Docker: https://docs.docker.com/get-docker/" "Docker is needed: https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 || die "Docker не отвечает — запустите его (или добавьте пользователя в группу docker) и повторите" "Docker does not answer — start it (or add your user to the docker group) and run again"
docker compose version >/dev/null 2>&1 || die "нужен docker compose v2" "docker compose v2 is needed"
GPU=0
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then GPU=1; fi
MEM_GB=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo 2>/dev/null || sysctl -n hw.memsize 2>/dev/null | awk '{printf "%d", $1/1024/1024/1024}' || echo 0)
say "Docker найден. Память: ${MEM_GB} ГБ, GPU NVIDIA: $([ $GPU = 1 ] && echo да || echo нет)" "Docker found. Memory: ${MEM_GB} GB, NVIDIA GPU: $([ $GPU = 1 ] && echo yes || echo no)"

# ---- menu helper: ask "title" default "opt1" "opt2" ... → number in REPLY -------------------
ask() {
  local title="$1" default="$2"; shift 2
  if [ "$YES" = 1 ]; then REPLY="$default"; return; fi
  printf '\n\033[1m%s\033[0m\n' "$title"
  local i=1; for o in "$@"; do printf '  %d) %s\n' "$i" "$o"; i=$((i+1)); done
  while :; do
    read -r -p "$(t "Выбор" "Choice") [$default]: " REPLY </dev/tty || REPLY=""
    REPLY="${REPLY:-$default}"
    [[ "$REPLY" =~ ^[0-9]+$ ]] && [ "$REPLY" -ge 1 ] && [ "$REPLY" -le $# ] && return
  done
}
prompt() { # prompt "text" "default" → REPLY
  if [ "$YES" = 1 ]; then REPLY="$2"; return; fi
  read -r -p "$1 [$2]: " REPLY </dev/tty || REPLY=""; REPLY="${REPLY:-$2}"
}

# ---- 1. model backend ----------------------------------------------------------------------
ask "$(t "1. Какую ИИ-модель использовать? Всё работает внутри вашей сети" "1. Which AI model to use? Everything runs inside your network")" "$([ $YES = 1 ] && echo 4 || echo 1)" \
  "$(t "Запустить модель на этой машине через Ollama (идёт в комплекте; видеокарта не обязательна)" "Run a model on this machine with Ollama (bundled; a GPU is optional)")" \
  "$(t "Запустить модель на этой машине через vLLM (нужна видеокарта NVIDIA; быстрее Ollama)" "Run a model on this machine with vLLM (needs an NVIDIA GPU; faster than Ollama)")" \
  "$(t "У нас уже есть модель — укажу её адрес (любой сервер с OpenAI-совместимым API: vLLM, Ollama, LM Studio, LiteLLM…)" "We already have a model — I will enter its address (any server with an OpenAI-compatible API: vLLM, Ollama, LM Studio, LiteLLM…)")" \
  "$(t "Пока без модели — только маскирование и демо" "No model for now — masking and the demo only")"
MODEL_CHOICE=$REPLY
PROFILES=""; LLM_MODEL=""; LLM_API_BASE=""; LLM_API_KEY="none"; OLLAMA_MODEL="gemma3:4b"; VLLM_MODEL="Qwen/Qwen3-8B"
case $MODEL_CHOICE in
  1)
    ask "$(t "Какую модель скачать (при первом запуске)" "Which model to download (on first start)")" 1 \
      "gemma3:4b   — $(t "~3 ГБ, от 8 ГБ памяти, без размышлений: быстрый ответ на CPU" "~3 GB, 8 GB RAM+, no thinking: fast answers on CPU")" \
      "gemma3:12b  — $(t "~8 ГБ, от 16 ГБ памяти, без размышлений" "~8 GB, 16 GB RAM+, no thinking")" \
      "qwen3:8b    — $(t "~5 ГБ, от 8 ГБ памяти, размышляющая: качественнее, но на CPU медленно" "~5 GB, 8 GB RAM+, thinking model: better, but slow on CPU")" \
      "gpt-oss:20b — $(t "~13 ГБ, от 16 ГБ памяти, размышляющая, лучше для кода; нужен GPU" "~13 GB, 16 GB RAM+, thinking, better at code; wants a GPU")" \
      "$(t "другая (ввести тег)" "other (type a tag)")"
    case $REPLY in 1) OLLAMA_MODEL=gemma3:4b ;; 2) OLLAMA_MODEL=gemma3:12b ;; 3) OLLAMA_MODEL=qwen3:8b ;; 4) OLLAMA_MODEL=gpt-oss:20b ;;
      5) prompt "$(t "Тег модели Ollama" "Ollama model tag")" "gemma3:4b"; OLLAMA_MODEL=$REPLY ;; esac
    PROFILES="ollama"; LLM_MODEL="ollama_chat/$OLLAMA_MODEL"; LLM_API_BASE="http://ollama:11434" ;;
  2)
    [ $GPU = 1 ] || say "внимание: GPU не найден, vLLM без него не запустится" "note: no GPU found, vLLM will not start without one"
    prompt "$(t "Модель vLLM (id с Hugging Face)" "vLLM model (Hugging Face id)")" "Qwen/Qwen3-8B"; VLLM_MODEL=$REPLY
    PROFILES="vllm"; LLM_MODEL="hosted_vllm/$VLLM_MODEL"; LLM_API_BASE="http://vllm:8000/v1" ;;
  3)
    prompt "$(t "Адрес вашей модели (с /v1); эта машина из контейнера видна как host.docker.internal" "Address of your model (with /v1); this machine is host.docker.internal from inside a container")" "http://host.docker.internal:11434/v1"; LLM_API_BASE=$REPLY
    prompt "$(t "Имя модели на этом сервере" "Model name served there")" "qwen3:8b"; LLM_MODEL="openai/$REPLY"
    prompt "$(t "Ключ доступа к серверу (если не нужен — none)" "Access key for that server (none if not needed)")" "none"; LLM_API_KEY=$REPLY ;;
  4) ;;
esac

# ---- 2. NER profile ------------------------------------------------------------------------
ask "$(t "2. Насколько тщательно искать имена и адреса? (Паспорта, СНИЛС, ИНН, карты, телефоны и ключи находятся при любом выборе)" "2. How thoroughly to look for names and addresses? (Passports, SNILS, INN, cards, phones and keys are found whichever you pick)")" 2 \
  "$(t "Не искать — только документы, номера и ключи по правилам; ~10 мс на запрос" "Do not — documents, numbers and keys by rules only; ~10 ms per request")" \
  "$(t "Быстро: spaCy (по умолчанию) — ~11 мс; пропускает 12 % персональных данных в шаблонных текстах и 40 % в живых переписках, в основном адреса" "Fast: spaCy (default) — ~11 ms; misses 12 % of personal data in templated texts and 40 % in real chats, mostly addresses")" \
  "$(t "Точно: ruBERT — ~150 мс; пропускает 3–5 %, адреса целиком; ещё ~1 ГБ памяти" "Accurate: ruBERT — ~150 ms; misses 3–5 %, whole addresses; ~1 GB more RAM")" \
  "$(t "Компромисс: DistilBERT — ~100 мс; пропускает 5 %, хуже ищет имена в живом тексте" "Middle ground: DistilBERT — ~100 ms; misses 5 %, weaker on names in free text")" \
  "$(t "GLiNER — ~1 с; пропускает 5–15 % и маскирует лишнее; не рекомендуем" "GLiNER — ~1 s; misses 5–15 % and overmasks; not recommended")"
NER=spacy; HF_MODEL=""; HF_MAP=""; GLINER=""
RU_MAP="FIRST_NAME=PERSON,LAST_NAME=PERSON,MIDDLE_NAME=PERSON,COUNTRY=LOCATION,REGION=LOCATION,DISTRICT=LOCATION,CITY=LOCATION,STREET=ADDRESS,HOUSE=ADDRESS"
case $REPLY in
  1) NER=none ;;
  2) NER=spacy ;;
  3) NER=none; HF_MODEL="redmadrobot-rnd/rubert-base-pii-ner"; HF_MAP="$RU_MAP" ;;
  4) NER=none; HF_MODEL="aule13/pii-guard-distilbert"; HF_MAP="$RU_MAP" ;;
  5) NER=none; GLINER="urchade/gliner_multi_pii-v1" ;;
esac

# ---- 3. passwords and secrets ----------------------------------------------------------------
ask "$(t "3. Как искать пароли и секреты? (Ключи AWS, GitHub, OpenAI и других сервисов по формату находятся при любом выборе)" "3. How to look for passwords and secrets? (AWS, GitHub, OpenAI and other service keys are found by format whichever you pick)")" 1 \
  "$(t "Правила + маленькая модель (по умолчанию) — находит 92 паролей из 100 в коде, логах и переписке; +5 мс; модель 0,7 МБ скачивается при первом запуске" "Rules + a small model (default) — finds 92 passwords in 100 in code, logs and chats; +5 ms; a 0.7 MB model is downloaded on first start")" \
  "$(t "Строго: модель только отсекает ложные срабатывания — находит 85 из 100, зато лишнего прячет втрое меньше; +3 мс" "Strict: the model only filters out false hits — finds 85 in 100, but hides a third as much by mistake; +3 ms")" \
  "$(t "Только правила — находит 86 из 100, но прячет лишнее в полтора раза чаще; ничего не скачивается" "Rules only — finds 86 in 100, but hides unrelated text 1.5× more often; nothing is downloaded")" \
  "$(t "Не искать пароли — только ключи известных форматов" "Do not look for passwords — known key formats only")"
case $REPLY in
  1) SECRETS=cascade ;;
  2) SECRETS=cascade-strict ;;
  3) SECRETS=rules ;;
  4) SECRETS=none ;;
esac

# ---- 4. ports ------------------------------------------------------------------------------
prompt "$(t "Порт шлюза (его адрес сотрудники укажут в своих программах)" "Gateway port (your people will point their tools at it)")" "${LITELLM_PORT:-4000}"; LITELLM_PORT=$REPLY
prompt "$(t "Порт демо" "Demo port")" "${DEMO_PORT:-8080}"; DEMO_PORT=$REPLY; ANALYZER_PORT="${ANALYZER_PORT:-3000}"

# ---- write .env (keep existing secrets) ----------------------------------------------------
keep() { [ -f .env ] && grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
MASTER="$(keep LITELLM_MASTER_KEY)"; SALT="$(keep LITELLM_SALT_KEY)"; PGPASS="$(keep POSTGRES_PASSWORD)"
rnd() { od -An -N16 -tx1 /dev/urandom | tr -d ' \n'; }
[ -n "$MASTER" ] && [ "$MASTER" != "sk-change-me" ] || MASTER="sk-$(rnd)"
[ -n "$SALT" ] && [ "$SALT" != "change-me-too" ] || SALT="$(rnd)"
[ -n "$PGPASS" ] && [ "$PGPASS" != "litellm" ] || PGPASS="$(rnd)"
COMPOSE_FILE="docker-compose.yml"; [ $GPU = 1 ] && [ -n "$PROFILES" ] && COMPOSE_FILE="docker-compose.yml:docker-compose.gpu.yml"
[ -f .env ] && cp .env ".env.bak.$(date +%Y%m%d%H%M%S)"
sed -e "s|^LLM_MODEL=.*|LLM_MODEL=$LLM_MODEL|" -e "s|^LLM_API_BASE=.*|LLM_API_BASE=$LLM_API_BASE|" -e "s|^LLM_API_KEY=.*|LLM_API_KEY=$LLM_API_KEY|" \
    -e "s|^COMPOSE_PROFILES=.*|COMPOSE_PROFILES=$PROFILES|" -e "s|^COMPOSE_FILE=.*|COMPOSE_FILE=$COMPOSE_FILE|" \
    -e "s|^OLLAMA_MODEL=.*|OLLAMA_MODEL=$OLLAMA_MODEL|" -e "s|^VLLM_MODEL=.*|VLLM_MODEL=$VLLM_MODEL|" \
    -e "s|^LITELLM_MASTER_KEY=.*|LITELLM_MASTER_KEY=$MASTER|" -e "s|^LITELLM_SALT_KEY=.*|LITELLM_SALT_KEY=$SALT|" -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$PGPASS|" \
    -e "s|^GUARDRAILS_NER=.*|GUARDRAILS_NER=$NER|" -e "s|^GUARDRAILS_HF_NER_MODEL=.*|GUARDRAILS_HF_NER_MODEL=$HF_MODEL|" \
    -e "s|^GUARDRAILS_HF_NER_MAPPING=.*|GUARDRAILS_HF_NER_MAPPING=$HF_MAP|" -e "s|^GUARDRAILS_GLINER_MODEL=.*|GUARDRAILS_GLINER_MODEL=$GLINER|" \
    -e "s|^GUARDRAILS_SECRETS=.*|GUARDRAILS_SECRETS=$SECRETS|" \
    -e "s|^LITELLM_PORT=.*|LITELLM_PORT=$LITELLM_PORT|" -e "s|^DEMO_PORT=.*|DEMO_PORT=$DEMO_PORT|" -e "s|^ANALYZER_PORT=.*|ANALYZER_PORT=$ANALYZER_PORT|" \
    .env.example > .env
say ".env записан" ".env written"

# ---- up ------------------------------------------------------------------------------------
say "собираю и запускаю (первый раз: образ анализатора ~3 ГБ, модели NER и LLM — по выбору)…" "building and starting (first time: analyzer image ~3 GB, NER/LLM models as chosen)…"
docker compose up -d --build
say "жду анализатор…" "waiting for the analyzer…"
for i in $(seq 1 120); do
  st="$(docker compose ps --format '{{.Name}} {{.Status}}' 2>/dev/null | grep analyzer || true)"
  echo "$st" | grep -q healthy && break
  echo "$st" | grep -qi "exited" && { docker compose logs --tail 30 analyzer; die "анализатор не поднялся — смотрите лог выше" "the analyzer did not start — see the log above"; }
  sleep 5
done
for i in $(seq 1 60); do curl -sf -o /dev/null "http://localhost:$LITELLM_PORT/health/liveliness" && break; sleep 3; done
if command -v python3 >/dev/null 2>&1; then python3 scripts/e2e_check.py --model mock || say "проверка маскирования не прошла — смотрите вывод выше" "the masking check failed — see the output above"; fi
[ -n "$PROFILES" ] && say "модель $LLM_MODEL скачивается в фоне; статус: docker compose logs -f ${PROFILES}-pull 2>/dev/null || docker compose logs -f $PROFILES" "model $LLM_MODEL is downloading in the background; status: docker compose logs -f ${PROFILES}-pull 2>/dev/null || docker compose logs -f $PROFILES"

printf '\n'
say "готово / ready:"
printf '  %s:  http://localhost:%s   (%s /ui, %s)\n' "$(t "Шлюз" "Gateway")" "$LITELLM_PORT" "$(t "админка" "admin UI")" "$(t "ключ администратора — LITELLM_MASTER_KEY в файле .env" "admin key — LITELLM_MASTER_KEY in .env")"
printf '  %s:  http://localhost:%s\n' "$(t "Демо" "Demo")" "$DEMO_PORT"
printf '  %s: docs/clients.md\n' "$(t "Как подключить Claude Code и другие программы" "How to connect Claude Code and other tools")"
