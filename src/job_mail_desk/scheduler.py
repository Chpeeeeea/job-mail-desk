from __future__ import annotations

import logging
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import DIGESTS_DIR, TASKS_DIR, Settings
from .digest import generate_digest
from .markdown_store import MarkdownTaskStore
from .notifier import notify_urgent
from .scanner import scan_once


LOGGER = logging.getLogger(__name__)


class ScheduledJobs:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.lock = threading.Lock()

    def scan(self) -> None:
        if not self.lock.acquire(blocking=False):
            LOGGER.info("上一次扫描尚未结束，本次跳过")
            return
        try:
            summary = scan_once(self.settings)
            notify_urgent(summary.urgent)
            LOGGER.info("扫描完成：%s", summary.to_dict())
        except Exception:
            LOGGER.exception("定时扫描失败")
        finally:
            self.lock.release()

    def digest(self, period: str) -> None:
        try:
            path = generate_digest(
                period,
                MarkdownTaskStore(TASKS_DIR),
                DIGESTS_DIR,
            )
            LOGGER.info("%s 简报已生成：%s", period, path)
        except Exception:
            LOGGER.exception("%s 简报生成失败", period)


def _add_jobs(
    scheduler: BackgroundScheduler | BlockingScheduler,
    settings: Settings,
) -> ScheduledJobs:
    jobs = ScheduledJobs(settings)
    common = {
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 3600,
    }
    scheduler.add_job(
        jobs.scan,
        IntervalTrigger(
            minutes=settings.poll_minutes,
            timezone=settings.timezone,
        ),
        id="mail-poll",
        replace_existing=True,
        next_run_time=datetime.now().astimezone(),
        **common,
    )
    scheduler.add_job(
        jobs.scan,
        CronTrigger(
            minute=settings.hourly_minute,
            timezone=settings.timezone,
        ),
        id="hourly-refresh",
        replace_existing=True,
        **common,
    )
    labels = ("morning", "noon", "evening")
    for label, time_value in zip(labels, settings.digest_times, strict=False):
        hour, minute = (int(part) for part in time_value.split(":", 1))
        scheduler.add_job(
            jobs.digest,
            CronTrigger(
                hour=hour,
                minute=minute,
                timezone=settings.timezone,
            ),
            args=(label,),
            id=f"digest-{label}",
            replace_existing=True,
            **common,
        )
    return jobs


def create_background_scheduler(settings: Settings) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.timezone)
    _add_jobs(scheduler, settings)
    return scheduler


def run_forever(settings: Settings) -> None:
    scheduler = BlockingScheduler(timezone=settings.timezone)
    _add_jobs(scheduler, settings)
    scheduler.start()

