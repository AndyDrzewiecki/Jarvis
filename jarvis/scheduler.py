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


def _run_consolidation() -> None:
    """Scheduled job: consolidate episodic memories into semantic knowledge."""
    try:
        from jarvis.consolidation import ConsolidationEngine
        engine = ConsolidationEngine()
        report = engine.run()
        logger.info(
            "Consolidation job done: episodes=%d created=%d reinforced=%d pruned=%d error=%s",
            report.episodes_processed, report.facts_created, report.facts_reinforced,
            report.episodes_pruned, report.error,
        )
    except Exception as exc:
        logger.error("Consolidation job failed: %s", exc)


def _run_long_term_grading() -> None:
    """Scheduled job: re-grade decisions from 7-30 days ago."""
    try:
        from jarvis.grading import DecisionGrader
        grader = DecisionGrader()
        count = grader.run_long_term_batch()
        logger.info("Long-term grading complete: %d decisions re-graded", count)
    except Exception as exc:
        logger.error("Long-term grading job failed: %s", exc)


def _run_guideline_evolution() -> None:
    """Scheduled job: evolve specialist guidelines based on graded decisions."""
    try:
        from jarvis.guideline_evolver import GuidelineEvolver
        evolver = GuidelineEvolver()
        for domain in ("grocery", "finance", "calendar", "weather"):
            result = evolver.evolve(domain)
            logger.info(
                "Guideline evolution %s: v%d→v%d patterns=%d corrective=%d reinforcement=%d",
                domain, result.old_version, result.new_version,
                result.patterns_analyzed, result.corrective_count, result.reinforcement_count,
            )
    except Exception as exc:
        logger.error("Guideline evolution job failed: %s", exc)


def _run_preference_mining() -> None:
    """Scheduled job: mine preference rules from recent interaction signals."""
    try:
        from jarvis.preference_learning import PreferenceMiner
        miner = PreferenceMiner()
        total = 0
        for domain in ("grocery", "finance", "calendar", "general"):
            count = miner.mine(domain=domain)
            total += count
        logger.info("Preference mining complete: %d rules upserted across all domains", total)
    except Exception as exc:
        logger.error("Preference mining job failed: %s", exc)


def _run_context_rebuild() -> None:
    """Scheduled job: rebuild specialist context engines."""
    try:
        from jarvis.context_engine import ContextEngine
        engine = ContextEngine()
        for domain in ("grocery", "finance", "calendar", "weather"):
            context = engine.rebuild(domain)
            logger.info(
                "Context rebuild %s: %d chars", domain, len(context)
            )
    except Exception as exc:
        logger.error("Context rebuild job failed: %s", exc)


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
    if config.ENGINES_ENABLED:
        try:
            import jarvis.engines.financial  # noqa: F401
            import jarvis.engines.research   # noqa: F401
            from jarvis.engines import ENGINE_REGISTRY
            from apscheduler.triggers.cron import CronTrigger
            for engine_cls in ENGINE_REGISTRY:
                engine_inst = engine_cls()
                _specialists.append(engine_inst)
                _scheduler.add_job(
                    _run_specialist_cycle,
                    trigger=CronTrigger.from_crontab(engine_inst.schedule),
                    args=[engine_inst.name],
                    id=f"engine_{engine_inst.name}",
                    replace_existing=True,
                )
                logger.info("Engine scheduled: %s (%s)", engine_inst.name, engine_inst.schedule)
        except Exception as exc:
            logger.error("Failed to register knowledge engines: %s", exc)

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

    if config.SPECIALISTS_ENABLED:
        _scheduler.add_job(
            _run_long_term_grading,
            trigger="cron",
            day_of_week="sun",
            hour=2,
            minute=0,
            id="long_term_grading",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_consolidation,
            trigger="cron",
            hour=3,
            minute=0,
            id="consolidation",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_guideline_evolution,
            trigger="cron",
            day=1,
            hour=4,
            minute=0,
            id="guideline_evolution",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_context_rebuild,
            trigger="cron",
            day_of_week="mon",
            hour=5,
            minute=0,
            id="context_rebuild",
            replace_existing=True,
        )
        _scheduler.add_job(
            _run_preference_mining,
            trigger="cron",
            day_of_week="sat",
            hour=4,
            minute=0,
            id="preference_mining",
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
