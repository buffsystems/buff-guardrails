# buff-guardrails analyzer: Presidio analyzer API + our recognizers + spaCy ru/en.
# CPU only. Optional NER models (GLiNER / HF) are enabled via env and cached in
# the /models volume on first start — nothing heavy beyond spaCy is baked in.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models \
    PORT=3000

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY buff_guardrails ./buff_guardrails
RUN pip install .[secrets] flask gunicorn \
 && python -m spacy download ru_core_news_lg \
 && python -m spacy download en_core_web_lg \
 && python -m spacy download ru_core_news_sm \
 && python -m spacy download en_core_web_sm

# Optional model backends are installed but idle unless GUARDRAILS_* enables them.
ARG WITH_MODELS=1
RUN if [ "$WITH_MODELS" = "1" ]; then \
      pip install --index-url https://download.pytorch.org/whl/cpu torch \
      && pip install "transformers>=4.40" "gliner>=0.2" gliner2 ; fi

COPY server.py ./
COPY conf ./conf

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s CMD curl -fs http://localhost:${PORT}/health || exit 1
EXPOSE 3000
CMD ["sh", "-c", "gunicorn -w ${WORKERS:-1} --threads 4 -t 180 -b 0.0.0.0:${PORT} server:app"]
