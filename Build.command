#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

IMAGE="catalog-app:latest"
OUT_DIR="dist/catalog-app"
ZIP_PATH="dist/catalog-app.zip"
PLATFORM="${PLATFORM:-linux/amd64}"
SRC_ENV="${SRC_ENV:-backend/.env}"

log() { printf '\033[1;36m[Build]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[Build]\033[0m %s\n' "$*" >&2; }

have_docker() {
    command -v docker >/dev/null 2>&1
}

docker_running() {
    docker info >/dev/null 2>&1
}

ensure_docker() {
    if ! have_docker; then
        err "Docker не найден. Установите Docker Desktop."
        read -rp "Нажмите Enter, чтобы закрыть окно…"
        exit 1
    fi
    if docker_running; then
        return 0
    fi
    log "Docker Desktop не запущен — открываю…"
    open -a Docker 2>/dev/null || true
    log "Жду, пока Docker поднимется (до 90 секунд)…"
    for _ in $(seq 1 90); do
        if docker_running; then
            log "Docker готов."
            return 0
        fi
        sleep 1
        printf '.'
    done
    echo
    err "Docker так и не стартовал за 90 секунд. Откройте Docker Desktop вручную и запустите Build.command ещё раз."
    read -rp "Нажмите Enter, чтобы закрыть окно…"
    exit 1
}

choose_platform() {
    if [[ -n "${PLATFORM_SET:-}" ]]; then
        return 0
    fi
    log "Для какой платформы собрать образ?"
    log "  [a] linux/amd64  — Intel Mac (как в прошлый раз)"
    log "  [s] linux/arm64  — Apple Silicon (этот Mac)"
    printf 'Выбор [a/s], Enter = a: '
    read -r -n1 answer || true
    echo
    case "${answer:-}" in
        s|S) PLATFORM="linux/arm64" ;;
        *)   PLATFORM="linux/amd64" ;;
    esac
}

git_sha() {
    if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        git rev-parse --short HEAD
    else
        echo "unknown"
    fi
}

build_image() {
    local sha
    sha="$(git_sha)"
    log "Собираю $IMAGE ($PLATFORM, GIT_SHA=$sha)…"
    docker buildx build \
        --platform "$PLATFORM" \
        --build-arg "GIT_SHA=$sha" \
        -t "$IMAGE" \
        --load \
        .
    log "Образ собран."
}

write_runtime_compose() {
    cat > "$OUT_DIR/docker-compose.yml" <<'EOF'
services:
  catalog:
    image: catalog-app:latest
    container_name: catalog-app
    ports:
      - "8000:8000"
    volumes:
      - catalog-data:/data
    env_file:
      - .env
    restart: unless-stopped

volumes:
  catalog-data:
EOF
}

write_runtime_env() {
    if [[ ! -f "$SRC_ENV" ]]; then
        err "Нет $SRC_ENV — откуда брать ключи для пакета."
        exit 1
    fi

    local openrouter_key openrouter_base openrouter_model
    local zai_key zai_base provider prompt_log_enabled

    openrouter_key="$(grep -E '^OPENROUTER_API_KEY=' "$SRC_ENV" | head -1 | cut -d= -f2-)"
    openrouter_base="$(grep -E '^OPENROUTER_BASE_URL=' "$SRC_ENV" | head -1 | cut -d= -f2-)"
    openrouter_model="$(grep -E '^OPENROUTER_DEFAULT_MODEL=' "$SRC_ENV" | head -1 | cut -d= -f2-)"
    zai_key="$(grep -E '^ZAI_API_KEY=' "$SRC_ENV" | head -1 | cut -d= -f2-)"
    zai_base="$(grep -E '^ZAI_BASE_URL=' "$SRC_ENV" | head -1 | cut -d= -f2-)"
    provider="$(grep -E '^APP_PROVIDER=' "$SRC_ENV" | head -1 | cut -d= -f2-)"
    prompt_log_enabled="$(grep -E '^PROMPT_LOG_ENABLED=' "$SRC_ENV" | head -1 | cut -d= -f2-)"

    [[ -n "$openrouter_base" ]] || openrouter_base="https://openrouter.ai/api/v1"
    [[ -n "$openrouter_model" ]] || openrouter_model="google/gemini-3.5-flash"
    [[ -n "$zai_base" ]] || zai_base="https://api.z.ai/api/coding/paas/v4"
    [[ -n "$provider" ]] || provider="zai"
    [[ -n "$prompt_log_enabled" ]] || prompt_log_enabled="true"

    cat > "$OUT_DIR/.env" <<EOF
OPENROUTER_API_KEY=${openrouter_key}
OPENROUTER_BASE_URL=${openrouter_base}
OPENROUTER_DEFAULT_MODEL=${openrouter_model}
APP_WORKSPACE=/data/workspace
APP_DB_PATH=/data/catalog.db
PROMPT_LOG_DIR=/data/prompt_logs
PROMPT_LOG_ENABLED=${prompt_log_enabled}
ZAI_BASE_URL=${zai_base}
ZAI_API_KEY=${zai_key}
APP_PROVIDER=${provider}
EOF
}

pack_zip() {
    local tmp_tar="dist/catalog-app.tar"

    mkdir -p dist
    rm -rf "$OUT_DIR"
    mkdir -p "$OUT_DIR"

    log "Сохраняю образ в tar…"
    docker save "$IMAGE" -o "$tmp_tar"
    mv "$tmp_tar" "$OUT_DIR/catalog-app.tar"

    write_runtime_compose
    write_runtime_env

    cp Catalog.command "$OUT_DIR/Catalog.command"
    cp README-RUN.md "$OUT_DIR/README-RUN.md"
    chmod +x "$OUT_DIR/Catalog.command"

    log "Упаковываю ${ZIP_PATH}..."
    rm -f "$ZIP_PATH"
    (
        cd dist
        zip -r catalog-app.zip catalog-app/ -x '*.DS_Store' >/dev/null
    )

    log "Готово: ${ZIP_PATH} ($(du -h "$ZIP_PATH" | awk '{print $1}'))"
    log "Платформа: ${PLATFORM} / GIT_SHA=$(git_sha)"
}

main() {
    if [[ ! -f Dockerfile ]] || [[ ! -f Catalog.command ]] || [[ ! -f README-RUN.md ]]; then
        err "Запускайте из корня репозитория Catalog (нужны Dockerfile, Catalog.command, README-RUN.md)."
        read -rp "Нажмите Enter, чтобы закрыть окно…"
        exit 1
    fi

    ensure_docker

    if [[ "${1:-}" == "--platform" && -n "${2:-}" ]]; then
        PLATFORM="$2"
        PLATFORM_SET=1
    elif [[ -n "${PLATFORM:-}" && "${PLATFORM}" != "linux/amd64" ]]; then
        PLATFORM_SET=1
    fi

    choose_platform
    build_image
    pack_zip

    open -R "$ZIP_PATH" 2>/dev/null || open dist 2>/dev/null || true
    echo
    read -rp "Нажмите Enter, чтобы закрыть окно…"
}

main "$@"
