"""
Jarvis background scheduler — APScheduler-based cron jobs.

Jobs:
  daily_brief    — fires at JARVIS_BRIEF_HOUR (default 8) local time,
                   generates a brief and pushes it to Discord.
  health_check   — runs every 15 minutes; HealthMonitor checks all adapters.
  workflow_check — runs every 30 minutes; WorkflowEngine evaluates triggers.

Config env vars:
  JARVIS_BRIEF_HOUR  — integer hour (0-23), default 8
  JARVIS_BRIEF_TZ    — pytz timezone string, default "America/Chicago"

Usage:
    from jarvis.scheduler import start, stop
    start()   # call once at server startup
    stop()    # call at server shutdown
"""
from __future__ import annotations
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

BRIEF_HOUR = int(os.getenv("JARVIS_BRIEF_HOUR", "8"))
BRIEF_TZ = os.getenv("JARVIS_BRIEF_TZ", "America/Chicago")
SPOKEN_BRIEF_HOUR = int(os.getenv("JARVIS_SPOKEN_BRIEF_HOUR", "8"))

_scheduler: Optional[object] = None  # BackgroundScheduler instance
_specialists: list = []


def _run_daily_brief() -> None:
    """Scheduled job: generate morning brief and push to Discord."""
    try:
        from jarvis.brief import BriefEngine
        engine = BriefEngine()
        result = engine.generate()
        logger.info("Daily brief generated. Sections: %s", result.get("sections"))
    except Exception as exc:
        logger.error("Daily brief job failed: %s", exc)


def _run_health_check() -> None:
    """Scheduled job: check all adapters for anomalies and push Discord alerts."""
    try:
        from jarvis.monitor import HealthMonitor
        monitor = HealthMonitor()
        alerts = monitor.check()
        if alerts:
            logger.info("Health check sent %d alert(s): %s", len(alerts), alerts)
        else:
            logger.debug("Health check complete. No alerts.")
    except Exception as exc:
        logger.error("Health check job failed: %s", exc)


def _run_spoken_brief_push() -> None:
    """Scheduled job: generate morning brief and push to all active WebSocket clients."""
    try:
        from jarvis.brief import BriefEngine
        engine = BriefEngine()
        result = engine.generate()
        brief_text = result.get("text", "")
        if not brief_text:
            logger.info("Spoken brief push: no text generated.")
            return
        # Lazy import from server to avoid circular import at module load.
        # APScheduler jobs run in threads — asyncio.run() creates a fresh event loop.
        import asyncio
        from server import push_to_all
        asyncio.run(push_to_all({"type": "speak", "text": brief_text}))
        logger.info("Spoken brief pushed to WebSocket clients.")
    except Exception as exc:
        logger.error("Spoken brief push job failed: %s", exc)


def _run_specialist_cycle(specialist_name: str) -> None:
    """Scheduled job: run one specialist's gather/analyze/improve cycle."""
    try:
        spec = next((s for s in _specialists if s.name == specialist_name), None)
        if spec is None:
            logger.warning("Specialist %r not found in registry", specialist_name)
            return
        report = spec.run_cycle()
        logger.info(
            "Specialist %s cycle done: gathered=%d insights=%d gaps=%d error=%s",
            specialist_name, report.gathered, report.insights, report.gaps_identified, report.error,
        )
    except Exception as exc:
        logger.error("Specialist cycle job failed for %s: %s", specialist_name, exc)


def _run_short_term_grading() -> None:
    """Scheduled job: grade yesterday's decisions."""
    try:
        from jarvis.grading import DecisionGrader
        grader = DecisionGrader()
        count = grader.run_short_term_batch()
        logger.info("Short-term grading complete: %d decisions graded", count)
    except Exception as exc:
        logger.error("Short-term grading job failed: %s", exc)


def _run_workflow_check() -> None:
    """Scheduled job: evaluate workflow triggers and fire/queue actions."""
    try:
        from jarvis.workflows import WorkflowEngine
        engine = WorkflowEngine()
        results = engine.run_checks()
        if results:
            logger.info("Workflow check: %d action(s): %s", len(results), results)
        else:
            logger.debug("Workflow check complete. No triggers fired.")
    except Exception as exc:
        logger.error("Workflow check job failed: %s", exc)


def start() -> None:
    """Start the background scheduler. Safe to call multiple times."""
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        import pytz
    except ImportError:
        logger.warning(
            "apscheduler/pytz not installed — scheduler disabled. "
            "Run: pip install apscheduler pytz"
        )
        return

    if _scheduler is not None and getattr(_scheduler, "running", False):
        return

    tz = pytz.timezone(BRIEF_TZ)
    _scheduler = BackgroundScheduler(timezone=tz)
    _scheduler.add_job(
        _run_daily_brief,
        trigger="cron",
        hour=BRIEF_HOUR,
        minute=0,
        id="daily_brief",
        replace_existing=True,
    )
    _scheduler.add_job(
        _run_health_check,
        trigger="interval",
        minutes=15,
        id="health_check",
        replace_existing=True,
    )
    _scheduler.add_job(
        _run_workflow_check,
        trigger="interval",
        minutes=30,
        id="workflow_check",
        replace_existing=True,
    )
    _scheduler.add_job(
        _run_spoken_brief_push,
        trigger="cron",
        hour=SPOKEN_BRIEF_HOUR,
        minute=0,
        id="spoken_brief_push",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started. Brief at %02d:00 %s. Spoken brief push at %02d:00. "
        "Health check every 15min. Workflows every 30min.",
        BRIEF_HOUR,
        BRIEF_TZ,
        SPOKEN_BRIEF_HOUR,
    )

    # Wire specialists if enabled
    global _specialists
    from jarvis import config
    if config.SPECIALISTS_ENABLED:
        try:
            from jarvis.specialists import start_all
            from apscheduler.triggers.cron import CronTrigger
            _specialists = start_all()
            for spec in _specialists:
                _scheduler.add_job(
                    _run_specialist_cycle,
                    trigger=CronTrigger.from_crontab(spec.schedule),
                    args=[spec.name],
                    id=f"specialist_{spec.name}",
                    replace_existing=True,
                )
                logger.info("Registered specialist %s on schedule %s", spec.name, spec.schedule)
        except Exception as exc:
            logger.error("Failed to register specialists: %s", exc)

    _scheduler.add_job(
        _run_short_term_grading,
        trigger="cron",
        hour=23,
        minute=0,
        id="short_term_grading",
        replace_existing=True,
    )


def stop() -> None:
    """Stop the background scheduler gracefully."""
    global _scheduler, _specialists
    if _scheduler is not None and getattr(_scheduler, "running", False):
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
    _scheduler = None
    _specialists = []
