FROM node:23-alpine AS frontend
WORKDIR /build
RUN corepack enable && corepack prepare pnpm@9 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build


FROM python:3.11-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
COPY backend/pyproject.toml ./
RUN pip install fastapi 'uvicorn[standard]' httpx pydantic python-dotenv jsonschema python-docx python-multipart dulwich
COPY backend/app ./app
COPY --from=frontend /build/dist ./static

ENV APP_WORKSPACE=/data/workspace \
    APP_DB_PATH=/data/catalog.db \
    PROMPT_LOG_DIR=/data/prompt_logs
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
