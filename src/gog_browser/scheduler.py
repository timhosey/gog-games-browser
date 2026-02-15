"""APScheduler: run full scan on schedule (cron or 'daily')."""

import asyncio
import logging
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from gog_browser.config import get_scan_schedule
from gog_browser.scan_flow import run_scan

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _run_scan_sync() -> None:
    """Called by scheduler in background thread; run async run_scan."""
    try:
        asyncio.run(run_scan())
    except Exception as e:
        logger.exception("Scheduled scan failed: %s", e)


def _parse_schedule(schedule: str) -> dict[str, Any] | None:
    """
    Parse GOG_SCAN_SCHEDULE. Supports:
    - "daily" or "day" -> 2am every day
    - Cron string "minute hour day month weekday" e.g. "0 2 * * *"
    Returns kwargs for add_job(trigger='cron', ...) or None if invalid/empty.
    """
    schedule = (schedule or "").strip().lower()
    if not schedule:
        return None
    if schedule in ("daily", "day"):
        return {"hour": 2, "minute": 0}
    parts = schedule.split()
    if len(parts) == 5:
        # cron: minute hour day month day_of_week
        return {
            "minute": parts[0],
            "hour": parts[1],
            "day": parts[2],
            "month": parts[3],
            "day_of_week": parts[4],
        }
    return None


def start_scheduler() -> None:
    """Start background scheduler if GOG_SCAN_SCHEDULE is set."""
    global _scheduler
    schedule = get_scan_schedule()
    cron_kw = _parse_schedule(schedule)
    if cron_kw is None:
        logger.info("No scan schedule set; only on-demand scan available.")
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_run_scan_sync, "cron", **cron_kw, id="gog_scan")
    _scheduler.start()
    logger.info("Scan scheduler started: %s", schedule)


def stop_scheduler() -> None:
    """Stop the background scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scan scheduler stopped.")
