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
EXPOSE 8000
CMD ["uvicorn", "drift.dashboard.server:app", "--host", "0.0.0.0", "--port", "8000"]
