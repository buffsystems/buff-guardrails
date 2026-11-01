# Demo: Vite/React UI built in a node stage, served by a small Flask backend
# that talks to the analyzer and to LiteLLM.
FROM node:22-alpine AS ui
WORKDIR /ui
RUN apk add --no-cache git
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=8080 STATIC_DIR=/app/static PRESETS_FILE=/app/presets.json
WORKDIR /app
RUN pip install flask gunicorn requests
COPY backend/app.py backend/masking.py ./
COPY presets.json ./
COPY --from=ui /ui/dist ./static
EXPOSE 8080
CMD ["sh", "-c", "gunicorn -w 2 --threads 4 -t 660 -b 0.0.0.0:${PORT} app:app"]
