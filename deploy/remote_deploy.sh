#!/usr/bin/env bash
# Выкатка МЭТР на сервере. Запускается из GitHub Actions по SSH:
#   ssh user@host 'bash -s' < deploy/remote_deploy.sh
#
# Логика: запомнить текущую версию → обновить код → пересобрать →
# дождаться здоровья приложения. Если не поднялось — откатиться на прошлую
# версию и вернуть ошибку. Прод не должен оставаться в нерабочем состоянии.
#
# .env на сервере не трогаем: он не в git, а `git reset --hard` не удаляет
# неотслеживаемые файлы.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/metr}"
HEALTH_URL="${HEALTH_URL:-http://localhost/health}"
BRANCH="${BRANCH:-main}"
TRIES=45          # 45 × 2 с = до 90 с на подъём (сборка образов уже позади)
SLEEP=2

cd "$APP_DIR"

PREV="$(git rev-parse HEAD)"
echo "→ Текущая версия: ${PREV:0:8}"

git fetch --all --prune
git reset --hard "origin/${BRANCH}"
NEW="$(git rev-parse HEAD)"
echo "→ Новая версия:   ${NEW:0:8}"
git --no-pager log --oneline -1

echo "→ Сборка и запуск контейнеров…"
docker compose up -d --build

echo "→ Проверка здоровья: ${HEALTH_URL}"
for i in $(seq 1 $TRIES); do
    if curl -fsS --max-time 5 "$HEALTH_URL" 2>/dev/null | grep -q '"status":[[:space:]]*"ok"'; then
        echo "✓ Приложение отвечает (попытка $i)"
        docker image prune -f >/dev/null 2>&1 || true
        echo "✓ Выкатка завершена: ${NEW:0:8}"
        exit 0
    fi
    sleep $SLEEP
done

echo "✗ Приложение не поднялось за $((TRIES * SLEEP)) с."
echo "  Последние строки логов web:"
docker compose logs --tail 40 web 2>&1 || true

if [ "$PREV" = "$NEW" ]; then
    echo "✗ Версия не менялась — откатываться некуда. Разбирайтесь по логам выше."
    exit 1
fi

echo "→ Откат на ${PREV:0:8}…"
git reset --hard "$PREV"
docker compose up -d --build
echo "✓ Откат выполнен. Прод работает на прежней версии."
exit 1
