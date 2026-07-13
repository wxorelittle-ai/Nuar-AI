"""Оркестрация сбора данных по всем конкурентам + сборка/отправка дайджеста.

Точка входа модуля. Запуск:
    python -m agents.competitor_scraper.scraper --dry-run   # печать в консоль
    python -m agents.competitor_scraper.scraper --once       # собрать + отправить

Логика:
  1. читаем config/competitors.yaml;
  2. по каждому конкуренту дёргаем парсеры 2ГИС / Яндекс / VK + СМИ;
  3. сохраняем свежий снимок в репозиторий;
  4. сравниваем с прошлой неделей → дайджест → Telegram.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone, timedelta

# На Windows консоль по умолчанию cp1251 и падает на эмодзи/кириллице в
# выводе. Принудительно переключаем потоки на UTF-8 (Python 3.7+).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

from config.settings import settings, load_competitors_config
from models.competitor import Competitor, CompetitorSnapshot
from db.repository import get_repository, Repository
from .parsers import dgis, yandex, vk, media
from . import digest as digest_mod

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("restopulse.scraper")

# Часовой пояс Тюмени (UTC+5), чтобы метка недели была локальной
TYUMEN_TZ = timezone(timedelta(hours=5))


def _week_label(now: datetime) -> str:
    """Человекочитаемая метка недели: «7–13 июля 2026»."""
    months = [
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]
    monday = now - timedelta(days=now.weekday())
    sunday = monday + timedelta(days=6)
    if monday.month == sunday.month:
        return f"{monday.day}–{sunday.day} {months[sunday.month - 1]} {sunday.year}"
    return (
        f"{monday.day} {months[monday.month - 1]} – "
        f"{sunday.day} {months[sunday.month - 1]} {sunday.year}"
    )


def collect_competitor(comp: Competitor, media_sources: list[dict], *, now: datetime) -> CompetitorSnapshot:
    """Собирает снимок по одному конкуренту из всех источников."""
    log.info("Сбор: %s", comp.name)
    snap = CompetitorSnapshot(
        competitor_name=comp.name,
        collected_at=now.isoformat(),
    )
    now_ts = int(now.timestamp())

    # Источники собираем последовательно (вежливый краулинг, без параллелизма)
    snap.sources["dgis"] = dgis.fetch(comp)
    snap.sources["yandex"] = yandex.fetch(comp)
    snap.sources["vk"] = vk.fetch(comp, now_ts=now_ts)

    for name, src in snap.sources.items():
        status = "ok" if src.ok else f"нет данных ({src.error})"
        log.info("  %s: %s", name, status)

    # Упоминания в городских СМИ
    try:
        snap.media_mentions = media.search(comp.name, media_sources)
        if snap.media_mentions:
            log.info("  СМИ: найдено упоминаний — %s", len(snap.media_mentions))
    except Exception as exc:  # СМИ — не критичный источник
        log.warning("  СМИ: ошибка поиска — %s", exc)

    return snap


def run(*, dry_run: bool = False, now: datetime | None = None) -> None:
    """Полный прогон: сбор → сохранение → дайджест → отправка."""
    now = now or datetime.now(TYUMEN_TZ)
    cfg = load_competitors_config()
    competitors = [Competitor.from_config(c) for c in cfg["competitors"]]
    media_sources = cfg["media_sources"]

    if not competitors:
        log.error("Список конкурентов пуст — заполните config/competitors.yaml")
        return

    repo: Repository = get_repository()
    collected_at_iso = now.isoformat()

    current: dict[str, CompetitorSnapshot] = {}
    for comp in competitors:
        snap = collect_competitor(comp, media_sources, now=now)
        current[comp.name] = snap
        # В dry-run не пишем в хранилище, чтобы не засорять историю тестовыми прогонами
        if not dry_run:
            repo.save_snapshot(snap)

    digest = digest_mod.build_digest(
        competitors=competitors,
        current_snapshots=current,
        repo=repo,
        week_label=_week_label(now),
        collected_at_iso=collected_at_iso,
    )
    digest_mod.send_digest(digest, repo, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="РестоПульс · Competitor Scraper Agent")
    parser.add_argument("--dry-run", action="store_true",
                        help="собрать и напечатать дайджест в консоль, ничего не отправляя и не сохраняя")
    parser.add_argument("--once", action="store_true",
                        help="боевой разовый прогон: собрать, сохранить снимок, отправить в Telegram")
    args = parser.parse_args()

    if not args.dry_run and not args.once:
        parser.error("укажите --dry-run или --once")

    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
