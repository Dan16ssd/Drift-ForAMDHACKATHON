# Stage 1: build the dashboard SPA
FROM node:22-slim AS spa
WORKDIR /build/dashboard
COPY dashboard/package*.json ./
RUN npm ci --no-fund --no-audit
COPY dashboard/ ./
RUN npm run build

# Stage 2: the app
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY drift/ drift/
RUN pip install --no-cache-dir ".[pg]"
COPY tests/fixtures/ tests/fixtures/
COPY --from=spa /build/dashboard/dist dashboard/dist
# Bake a finished demo: mock-mode replay of the drift fixture (no keys needed).
# The image then serves a dashboard with a full story — hearings, the ALERT,
# the countdown, and the outcome-graded receipt — the moment it starts.
RUN python -m drift.streams.replay tests/fixtures/drift_stream.jsonl \
      --db sqlite:////app/demo.db --quiet
ENV DATABASE_URL=sqlite:////app/demo.db
EXPOSE 8000
CMD ["sh", "-c", "uvicorn drift.dashboard.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
