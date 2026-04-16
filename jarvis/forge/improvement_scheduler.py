"""ImprovementScheduler — continuous improvement and monthly retrain trigger.

Orchestrates the full self-improvement cycle on a schedule:

  Daily (nightly):
    1. Run AgentTrainer.review_all() — grade output quality, update prompt versions
    2. Run PatternAnalyst.analyze_all() — identify failure trends
    3. Run AgentTester.test_all_staged() — promote or discard fixes
    4. Write improvement report to blackboard

  Weekly:
    1. Export training data (correction pairs + high-quality interactions)
    2. Check whether retraining threshold is met (N pairs, time since last train)
    3. Stage LoRA job if threshold is met

  Monthly:
    1. Launch LoRA fine-tuning job if staged and hardware is available
    2. Monitor training to completion
    3. Publish adapter to Ollama if successful
    4. Write full improvement cycle report

Schedule persistence: jobs are stored in data/forge.db (improvement_schedule table).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

_SCHEDULE_DB = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "forge.db"
)

_DDL = """
CREATE TABLE IF NOT EXISTS improvement_schedule (
    id          TEXT PRIMARY KEY,
    cycle_type  TEXT NOT NULL,   -- daily | weekly | monthly
    status      TEXT DEFAULT 'pending',
    scheduled_at TEXT NOT NULL,
    started_at  TEXT,
    completed_at TEXT,
    report      TEXT,
    error       TEXT
);

CREATE TABLE IF NOT EXISTS improvement_config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

# Default thresholds
_DEFAULT_CONFIG = {
    "daily_run_hour":           "2",    # 2am UTC nightly
    "weekly_run_day":           "0",    # Monday
    "monthly_run_day":          "1",    # 1st of month
    "min_pairs_for_training":   "100",  # need 100 correction pairs before training
    "min_days_between_trains":  "30",   # at least 30 days between training runs
    "auto_launch_training":     "false", # require manual approval by default
    "training_backend":         "axolotl",
    "training_base_model":      "Qwen/Qwen2.5-0.5B",
    "training_host":            "192.168.111.27",  # Mini PC worker node
}


@dataclass
class ImprovementReport:
    """Summary of one improvement cycle."""
    cycle_type: str
    cycle_id: str
    started_at: str
    completed_at: str
    # Daily fields
    agents_reviewed: int = 0
    prompts_updated: int = 0
    patterns_identified: int = 0
    proposals_staged: int = 0
    ab_tests_run: int = 0
    promotions: int = 0
    # Weekly fields
    training_pairs_exported: int = 0
    training_threshold_met: bool = False
    lora_job_staged: str | None = None
    # Monthly fields
    training_launched: bool = False
    training_job_id: str | None = None
    training_status: str | None = None
    # Common
    errors: list[str] = field(default_factory=list)
    blackboard_alert: str = ""


class ImprovementScheduler:
    """Runs the full self-improvement cycle on schedule.

    Usage::

        scheduler = ImprovementScheduler()

        # Run cycles manually (normally triggered by Jarvis scheduler)
        scheduler.run_daily()
        scheduler.run_weekly()
        scheduler.run_monthly()

        # Check schedule
        status = scheduler.get_schedule_status()
        print(status["last_daily"], status["next_monthly"])

        # Configure thresholds
        scheduler.set_config("min_pairs_for_training", "200")
    """

    def __init__(self, db_path: str | None = None):
        self._db = db_path or _SCHEDULE_DB
        self._init_db()

    # ------------------------------------------------------------------
    # Cycle runners
    # ------------------------------------------------------------------

    def run_daily(self) -> ImprovementReport:
        """Nightly improvement cycle: review, analyze, test."""
        cycle_id = self._start_cycle("daily")
        started_at = datetime.now(timezone.utc).isoformat()
        errors: list[str] = []

        agents_reviewed = prompts_updated = patterns_identified = 0
        proposals_staged = ab_tests_run = promotions = 0

        # Step 1: AgentTrainer — review all agents
        try:
            from jarvis.forge.trainer import AgentTrainer
            trainer = AgentTrainer()
            reports = trainer.review_all(min_interactions=5)
            agents_reviewed = len(reports)
            prompts_updated = sum(1 for r in reports if r.new_prompt_version is not None)
            logger.info("ImprovementScheduler daily: reviewed %d agents, updated %d prompts",
                        agents_reviewed, prompts_updated)
        except Exception as exc:
            errors.append(f"Trainer error: {exc}")
            logger.warning("ImprovementScheduler daily trainer error: %s", exc)

        # Step 2: PatternAnalyst — identify trends
        try:
            from jarvis.forge.pattern_analyst import PatternAnalyst
            analyst = PatternAnalyst()
            trend_reports = analyst.analyze_all(window=500)
            patterns_identified = sum(len(r.patterns_identified) for r in trend_reports)
            proposals_staged = sum(r.proposals_staged for r in trend_reports)
            logger.info("ImprovementScheduler daily: identified %d patterns, staged %d proposals",
                        patterns_identified, proposals_staged)
        except Exception as exc:
            errors.append(f"PatternAnalyst error: {exc}")
            logger.warning("ImprovementScheduler daily analyst error: %s", exc)

        # Step 3: AgentTester — A/B test staged proposals
        try:
            from jarvis.forge.tester import AgentTester
            tester = AgentTester()
            test_reports = tester.test_all_staged(n_runs=3)
            ab_tests_run = len(test_reports)
            promotions = sum(1 for r in test_reports if r.decision == "promoted")
            logger.info("ImprovementScheduler daily: ran %d A/B tests, promoted %d",
                        ab_tests_run, promotions)
        except Exception as exc:
            errors.append(f"AgentTester error: {exc}")
            logger.warning("ImprovementScheduler daily tester error: %s", exc)

        completed_at = datetime.now(timezone.utc).isoformat()
        blackboard_msg = (
            f"Daily improvement: {agents_reviewed} agents reviewed, "
            f"{prompts_updated} prompts updated, {promotions} fixes promoted."
        )

        report = ImprovementReport(
            cycle_type="daily",
            cycle_id=cycle_id,
            started_at=started_at,
            completed_at=completed_at,
            agents_reviewed=agents_reviewed,
            prompts_updated=prompts_updated,
            patterns_identified=patterns_identified,
            proposals_staged=proposals_staged,
            ab_tests_run=ab_tests_run,
            promotions=promotions,
            errors=errors,
            blackboard_alert=blackboard_msg,
        )

        self._complete_cycle(cycle_id, report)
        self._post_to_blackboard("improvement_daily", blackboard_msg, errors)
        return report

    def run_weekly(self) -> ImprovementReport:
        """Weekly cycle: export training data and check retraining threshold."""
        cycle_id = self._start_cycle("weekly")
        started_at = datetime.now(timezone.utc).isoformat()
        errors: list[str] = []

        pairs_exported = 0
        threshold_met = False
        lora_job_staged: str | None = None

        try:
            from jarvis.forge.training_exporter import TrainingExporter
            exporter = TrainingExporter()
            stats_list = exporter.export_all()
            pairs_exported = sum(s.total_pairs for s in stats_list)
            logger.info("ImprovementScheduler weekly: exported %d training pairs", pairs_exported)
        except Exception as exc:
            errors.append(f"Export error: {exc}")
            logger.warning("ImprovementScheduler weekly export error: %s", exc)

        # Check training threshold
        min_pairs = int(self.get_config("min_pairs_for_training"))
        min_days = int(self.get_config("min_days_between_trains"))
        last_monthly = self._last_completed("monthly")

        days_since_last = 999
        if last_monthly:
            try:
                last_dt = datetime.fromisoformat(last_monthly)
                days_since_last = (datetime.now(timezone.utc) - last_dt).days
            except Exception:
                pass

        threshold_met = pairs_exported >= min_pairs and days_since_last >= min_days

        if threshold_met:
            # Stage a LoRA job for next monthly cycle
            try:
                from jarvis.forge.lora_runner import LoraRunner
                from jarvis.forge.training_exporter import TrainingExporter
                runner = LoraRunner()
                exporter = TrainingExporter()
                stats = exporter.export_corrections(format="sharegpt", mark_used=False)
                if stats.output_path:
                    job = runner.create_job(
                        name=f"jarvis-weekly-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                        data_path=stats.output_path,
                        backend=self.get_config("training_backend"),
                        base_model=self.get_config("training_base_model"),
                    )
                    lora_job_staged = job.id
                    logger.info("ImprovementScheduler weekly: staged LoRA job %s", job.id)
            except Exception as exc:
                errors.append(f"LoRA staging error: {exc}")
                logger.warning("ImprovementScheduler weekly LoRA staging error: %s", exc)

        completed_at = datetime.now(timezone.utc).isoformat()
        blackboard_msg = (
            f"Weekly improvement: {pairs_exported} training pairs exported. "
            f"Threshold {'MET' if threshold_met else 'not met'} "
            f"({pairs_exported}/{min_pairs} pairs, {days_since_last}/{min_days} days)."
            + (f" LoRA job staged: {lora_job_staged}" if lora_job_staged else "")
        )

        report = ImprovementReport(
            cycle_type="weekly",
            cycle_id=cycle_id,
            started_at=started_at,
            completed_at=completed_at,
            training_pairs_exported=pairs_exported,
            training_threshold_met=threshold_met,
            lora_job_staged=lora_job_staged,
            errors=errors,
            blackboard_alert=blackboard_msg,
        )
        self._complete_cycle(cycle_id, report)
        self._post_to_blackboard("improvement_weekly", blackboard_msg, errors)
        return report

    def run_monthly(self) -> ImprovementReport:
        """Monthly cycle: launch LoRA training if threshold met and job is staged."""
        cycle_id = self._start_cycle("monthly")
        started_at = datetime.now(timezone.utc).isoformat()
        errors: list[str] = []

        training_launched = False
        training_job_id: str | None = None
        training_status: str | None = None

        auto_launch = self.get_config("auto_launch_training").lower() in ("true", "1", "yes")

        try:
            from jarvis.forge.lora_runner import LoraRunner
            runner = LoraRunner()
            pending_jobs = runner.list_jobs(status="pending")

            if pending_jobs and auto_launch:
                job = pending_jobs[0]  # Launch the most recently created staged job
                training_job_id = job.id
                logger.info("ImprovementScheduler monthly: launching LoRA job %s", job.id)

                # Configure then launch
                runner.configure(job.id)
                host = self.get_config("training_host") or None
                result = runner.launch(
                    job.id,
                    remote_host=host if host and host != "local" else None,
                )
                training_launched = result in ("launched", "dry_run")
                training_status = result
            elif pending_jobs:
                training_job_id = pending_jobs[0].id
                training_status = "pending_approval"
                logger.info(
                    "ImprovementScheduler monthly: job %s ready but auto_launch=false, needs approval",
                    pending_jobs[0].id,
                )
            else:
                training_status = "no_jobs_staged"
                logger.info("ImprovementScheduler monthly: no LoRA jobs staged")

        except Exception as exc:
            errors.append(f"Monthly training error: {exc}")
            logger.warning("ImprovementScheduler monthly error: %s", exc)

        completed_at = datetime.now(timezone.utc).isoformat()
        if training_launched:
            blackboard_msg = f"Monthly training LAUNCHED: job {training_job_id} running on {self.get_config('training_host')}."
        elif training_status == "pending_approval":
            blackboard_msg = f"Monthly training READY: job {training_job_id} staged and waiting for approval (auto_launch=false)."
        else:
            blackboard_msg = "Monthly check: no training jobs ready."

        report = ImprovementReport(
            cycle_type="monthly",
            cycle_id=cycle_id,
            started_at=started_at,
            completed_at=completed_at,
            training_launched=training_launched,
            training_job_id=training_job_id,
            training_status=training_status,
            errors=errors,
            blackboard_alert=blackboard_msg,
        )
        self._complete_cycle(cycle_id, report)
        self._post_to_blackboard("improvement_monthly", blackboard_msg, errors)
        return report

    # ------------------------------------------------------------------
    # Schedule management
    # ------------------------------------------------------------------

    def get_schedule_status(self) -> dict[str, Any]:
        """Return last run times and next scheduled runs for each cycle."""
        conn = self._open()
        result: dict[str, Any] = {}
        for cycle_type in ("daily", "weekly", "monthly"):
            row = conn.execute(
                "SELECT * FROM improvement_schedule"
                " WHERE cycle_type = ? AND status = 'completed'"
                " ORDER BY completed_at DESC LIMIT 1",
                (cycle_type,),
            ).fetchone()
            result[f"last_{cycle_type}"] = dict(row)["completed_at"] if row else None

        conn.close()

        now = datetime.now(timezone.utc)
        result["next_daily"]   = self._next_run("daily", now).isoformat()
        result["next_weekly"]  = self._next_run("weekly", now).isoformat()
        result["next_monthly"] = self._next_run("monthly", now).isoformat()
        return result

    def is_due(self, cycle_type: str) -> bool:
        """Check whether a cycle is overdue."""
        last = self._last_completed(cycle_type)
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(last)
            if cycle_type == "daily":
                return (datetime.now(timezone.utc) - last_dt) > timedelta(hours=20)
            elif cycle_type == "weekly":
                return (datetime.now(timezone.utc) - last_dt) > timedelta(days=6)
            elif cycle_type == "monthly":
                return (datetime.now(timezone.utc) - last_dt) > timedelta(days=28)
        except Exception:
            return True
        return False

    def run_due(self) -> list[ImprovementReport]:
        """Run all overdue cycles. Called by the Jarvis scheduler."""
        reports = []
        for cycle_type in ("monthly", "weekly", "daily"):
            if self.is_due(cycle_type):
                try:
                    if cycle_type == "daily":
                        reports.append(self.run_daily())
                    elif cycle_type == "weekly":
                        reports.append(self.run_weekly())
                    elif cycle_type == "monthly":
                        reports.append(self.run_monthly())
                except Exception as exc:
                    logger.error("ImprovementScheduler.run_due %s error: %s", cycle_type, exc)
        return reports

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def get_config(self, key: str) -> str:
        conn = self._open()
        row = conn.execute(
            "SELECT value FROM improvement_config WHERE key = ?", (key,)
        ).fetchone()
        conn.close()
        return row[0] if row else _DEFAULT_CONFIG.get(key, "")

    def set_config(self, key: str, value: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._open()
        conn.execute(
            "INSERT OR REPLACE INTO improvement_config (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now),
        )
        conn.commit()
        conn.close()

    def get_all_config(self) -> dict[str, str]:
        conn = self._open()
        rows = conn.execute("SELECT key, value FROM improvement_config").fetchall()
        conn.close()
        config = dict(_DEFAULT_CONFIG)
        config.update({r[0]: r[1] for r in rows})
        return config

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _start_cycle(self, cycle_type: str) -> str:
        now = datetime.now(timezone.utc).isoformat()
        cycle_id = str(uuid.uuid4())
        conn = self._open()
        conn.execute(
            "INSERT INTO improvement_schedule (id, cycle_type, status, scheduled_at, started_at)"
            " VALUES (?, ?, 'running', ?, ?)",
            (cycle_id, cycle_type, now, now),
        )
        conn.commit()
        conn.close()
        return cycle_id

    def _complete_cycle(self, cycle_id: str, report: ImprovementReport) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._open()
        conn.execute(
            "UPDATE improvement_schedule SET status='completed', completed_at=?, report=?"
            " WHERE id=?",
            (now, json.dumps({
                "agents_reviewed": report.agents_reviewed,
                "prompts_updated": report.prompts_updated,
                "promotions": report.promotions,
                "training_pairs_exported": report.training_pairs_exported,
                "training_launched": report.training_launched,
                "training_job_id": report.training_job_id,
                "errors": report.errors,
            }), cycle_id),
        )
        conn.commit()
        conn.close()

    def _last_completed(self, cycle_type: str) -> str | None:
        conn = self._open()
        row = conn.execute(
            "SELECT completed_at FROM improvement_schedule"
            " WHERE cycle_type = ? AND status = 'completed'"
            " ORDER BY completed_at DESC LIMIT 1",
            (cycle_type,),
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def _next_run(self, cycle_type: str, now: datetime) -> datetime:
        """Estimate the next scheduled run time."""
        last = self._last_completed(cycle_type)
        if not last:
            return now
        try:
            last_dt = datetime.fromisoformat(last)
        except Exception:
            return now

        if cycle_type == "daily":
            return last_dt + timedelta(hours=24)
        elif cycle_type == "weekly":
            return last_dt + timedelta(days=7)
        elif cycle_type == "monthly":
            return last_dt + timedelta(days=30)
        return now

    def _post_to_blackboard(self, event: str, message: str, errors: list[str]) -> None:
        try:
            from jarvis.blackboard import SharedBlackboard
            bb = SharedBlackboard()
            payload = {"event": event, "message": message}
            if errors:
                payload["errors"] = errors
            bb.post(source="improvement_scheduler", event=event, payload=payload)
        except Exception as exc:
            logger.debug("ImprovementScheduler: blackboard post failed (non-critical): %s", exc)

    def _init_db(self) -> None:
        conn = self._open()
        conn.executescript(_DDL)
        conn.commit()
        conn.close()

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
