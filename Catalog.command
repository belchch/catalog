#!/usr/bin/env bash
set -euo pipefail

# Folder of this script (resolves symlinks — works when user double-clicks
# from anywhere, including /Applications).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CATALOG_URL="http://localhost:8000"
HEALTH_URL="$CATALOG_URL/health"

log() { printf '\033[1;36m[Catalog]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[Catalog]\033[0m %s\n' "$*" >&2; }

have_docker() {
    command -v docker >/dev/null 2>&1
}

docker_running() {
    docker info >/dev/null 2>&1
}

ensure_docker() {
    if ! have_docker; then
        err "Docker не найден. Установите Docker Desktop (см. README-RUN.md)."
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
    err "Docker так и не стартовал за 90 секунд. Откройте Docker Desktop вручную и запустите Catalog.command ещё раз."
    read -rp "Нажмите Enter, чтобы закрыть окно…"
    exit 1
}

is_catalog_running() {
    curl -fsS "$HEALTH_URL" >/dev/null 2>&1
}

stop_catalog() {
    log "Останавливаю Catalog…"
    docker compose down
}

start_catalog() {
    if is_catalog_running; then
        log "Catalog уже запущен. Открываю браузер."
        open "$CATALOG_URL"
        return 0
    fi

    if ! docker image inspect catalog-app:latest >/dev/null 2>&1; then
        if [[ -f catalog-app.tar ]]; then
            log "Загружаю образ из catalog-app.tar (первый запуск, ~30 секунд)…"
            docker load -i catalog-app.tar
        else
            err "Образ catalog-app:latest не найден и нет catalog-app.tar рядом со скриптом."
            exit 1
        fi
    fi

    log "Запускаю контейнер…"
    docker compose up -d

    log "Жду ответа от Catalog (до 60 секунд)…"
    for _ in $(seq 1 60); do
        if is_catalog_running; then
            log "Готово!"
            open "$CATALOG_URL"
            return 0
        fi
        sleep 1
        printf '.'
    done
    echo
    err "Catalog не ответил за 60 секунд. Последние логи контейнера:"
    docker logs --tail 30 catalog-app 2>&1 || true
    read -rp "Нажмите Enter, чтобы закрыть окно…"
    exit 1
}

main() {
    ensure_docker

    if is_catalog_running; then
        log "Catalog запущен. Можно остановить (S) или открыть в браузере (любая другая клавиша)? [s/O]"
        read -r -n1 answer
        echo
        case "$answer" in
            s|S) stop_catalog ;;
            *)   open "$CATALOG_URL" ;;
        esac
        exit 0
    fi

    start_catalog
}

main
