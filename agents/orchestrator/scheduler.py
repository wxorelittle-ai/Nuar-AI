"""Оркестратор МЭТРА: фоновые задачи по расписанию.

  • еженедельный разведдайджест по конкурентам (competitor_scraper);
  • автопубликация утверждённых постов, у которых наступило время (каждую минуту).

MVP на APScheduler; в проде задачи можно вынести в системный cron / Celery.

Запуск:
    python -m agents.orchestrator.scheduler
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config.settings import settings
from agents.competitor_scraper import scraper
from agents.content import service as content

log = logging.getLogger("restopulse.scheduler")


def _digest_job() -> None:
    log.info("▶ Плановый запуск разведдайджеста")
    try:
        scraper.run(dry_run=False)
    except Exception:  # планировщик не должен умирать из-за одного прогона
        log.exception("Ошибка в плановом прогоне")


def _autopublish_job() -> None:
    try:
        published = content.auto_publish_due()
        if published:
            log.info("Автоопубликовано постов: %s", len(published))
    except Exception:
        log.exception("Ошибка автопубликации")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    sched = BlockingScheduler(timezone=settings.timezone)
    trigger = CronTrigger(
        day_of_week=settings.digest_cron_day_of_week,
        hour=settings.digest_cron_hour,
        minute=settings.digest_cron_minute,
        timezone=settings.timezone,
    )
    sched.add_job(_digest_job, trigger, id="weekly_digest", replace_existing=True)
    # Автопубликация запланированных постов — раз в минуту
    sched.add_job(_autopublish_job, IntervalTrigger(minutes=1), id="autopublish", replace_existing=True)
    log.info(
        "Планировщик запущен. Дайджест: %s %02d:%02d (%s). Автопубликация: каждую минуту. Ctrl+C для остановки.",
        settings.digest_cron_day_of_week,
        settings.digest_cron_hour,
        settings.digest_cron_minute,
        settings.timezone,
    )
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Планировщик остановлен")


if __name__ == "__main__":
    main()
