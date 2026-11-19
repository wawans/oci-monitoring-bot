"""Dynamic background scheduler manager with runtime rescheduling (ADR-006)."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import func, select

from src.database.connection import get_bot_setting
from src.database.models import BillingSnapshot, InstanceState
from src.scheduler.tasks import AlertCallback, poll_billing_task, poll_metrics_task

logger = logging.getLogger(__name__)


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure datetime object is timezone-aware in UTC format."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class SchedulerManager:
    """Manages APScheduler lifecycle and dynamic job rescheduling for OCI monitoring."""

    JOB_ID_METRICS = "job_poll_metrics"
    JOB_ID_BILLING = "job_poll_billing"

    VALID_METRICS_INTERVALS_MINUTES = {5, 10, 30}
    VALID_BILLING_INTERVALS_HOURS = {3, 6, 12}

    def __init__(
        self,
        client_factory: Any,
        compute_service: Any,
        monitoring_service: Any,
        billing_service: Any,
        session_factory: Any,
        alert_callback: Optional[AlertCallback] = None,
    ) -> None:
        self.client_factory = client_factory
        self.compute_service = compute_service
        self.monitoring_service = monitoring_service
        self.billing_service = billing_service
        self.session_factory = session_factory
        self.alert_callback = alert_callback

        self.scheduler: AsyncIOScheduler = AsyncIOScheduler()
        self.current_metrics_interval: int = 10
        self.current_billing_interval: int = 6

    def start(
        self,
        metrics_interval_minutes: int = 10,
        billing_interval_hours: int = 6,
    ) -> None:
        """Start the background scheduler with configured polling intervals.

        Args:
            metrics_interval_minutes: Interval for VM and CPU metrics in minutes (5, 10, 30).
            billing_interval_hours: Interval for billing polling in hours (3, 6, 12).
        """
        self.current_metrics_interval = metrics_interval_minutes
        self.current_billing_interval = billing_interval_hours

        # Schedule Metrics & Lifecycle Task
        self.scheduler.add_job(
            poll_metrics_task,
            trigger=IntervalTrigger(minutes=self.current_metrics_interval),
            id=self.JOB_ID_METRICS,
            name="OCI Compute & Metrics Poller",
            replace_existing=True,
            kwargs={
                "client_factory": self.client_factory,
                "compute_service": self.compute_service,
                "monitoring_service": self.monitoring_service,
                "session_factory": self.session_factory,
                "alert_callback": self.alert_callback,
            },
        )

        # Schedule Billing & Forecast Task
        self.scheduler.add_job(
            poll_billing_task,
            trigger=IntervalTrigger(hours=self.current_billing_interval),
            id=self.JOB_ID_BILLING,
            name="OCI Billing & Forecast Poller",
            replace_existing=True,
            kwargs={
                "client_factory": self.client_factory,
                "billing_service": self.billing_service,
                "session_factory": self.session_factory,
                "alert_callback": self.alert_callback,
            },
        )

        self.scheduler.start()
        logger.info(
            "Scheduler started. Metrics interval: %dm, Billing interval: %dh",
            self.current_metrics_interval,
            self.current_billing_interval,
        )

    def reschedule_metrics(self, new_interval_minutes: int) -> bool:
        """Dynamically reschedule the compute & metrics polling interval at runtime.

        Args:
            new_interval_minutes: New interval in minutes.

        Returns:
            True if job was successfully rescheduled, False otherwise.
        """
        try:
            self.scheduler.reschedule_job(
                self.JOB_ID_METRICS,
                trigger=IntervalTrigger(minutes=new_interval_minutes),
            )
            self.current_metrics_interval = new_interval_minutes
            logger.info("Rescheduled metrics poller to %d minutes.", new_interval_minutes)
            return True
        except Exception as e:
            logger.error("Failed to reschedule metrics poller: %s", e)
            return False

    def reschedule_billing(self, new_interval_hours: int) -> bool:
        """Dynamically reschedule the billing & forecast polling interval at runtime.

        Args:
            new_interval_hours: New interval in hours.

        Returns:
            True if job was successfully rescheduled, False otherwise.
        """
        try:
            self.scheduler.reschedule_job(
                self.JOB_ID_BILLING,
                trigger=IntervalTrigger(hours=new_interval_hours),
            )
            self.current_billing_interval = new_interval_hours
            logger.info("Rescheduled billing poller to %d hours.", new_interval_hours)
            return True
        except Exception as e:
            logger.error("Failed to reschedule billing poller: %s", e)
            return False

    async def trigger_metrics_poll(self) -> int:
        """Immediately execute a compute and metrics polling cycle.

        Returns:
            Number of compute instances evaluated.
        """
        return await poll_metrics_task(
            client_factory=self.client_factory,
            compute_service=self.compute_service,
            monitoring_service=self.monitoring_service,
            session_factory=self.session_factory,
            alert_callback=self.alert_callback,
        )

    async def trigger_billing_poll(self) -> int:
        """Immediately execute a billing and forecast polling cycle.

        Returns:
            Number of accounts successfully polled.
        """
        return await poll_billing_task(
            client_factory=self.client_factory,
            billing_service=self.billing_service,
            session_factory=self.session_factory,
            alert_callback=self.alert_callback,
        )

    async def get_latest_metrics_timestamp(self) -> Optional[datetime]:
        """Retrieve most recent metrics update timestamp across instance_state and bot_settings.

        Returns:
            Timezone-aware UTC datetime of latest update, or None if no data exists.
        """
        async with self.session_factory() as session:
            # 1. From InstanceState
            res = await session.execute(select(func.max(InstanceState.last_seen)))
            db_max = res.scalar()

            # 2. From bot_settings key 'last_poll_metrics_at'
            setting_val = await get_bot_setting(session, "last_poll_metrics_at")
            setting_dt: Optional[datetime] = None
            if setting_val:
                try:
                    setting_dt = datetime.fromisoformat(setting_val)
                except ValueError:
                    pass

            candidates: list[datetime] = []
            for dt in (db_max, setting_dt):
                if dt is not None:
                    ensured = _ensure_utc(dt)
                    if ensured is not None:
                        candidates.append(ensured)
            return max(candidates) if candidates else None

    async def get_latest_billing_timestamp(self) -> Optional[datetime]:
        """Retrieve most recent billing snapshot timestamp across billing_snapshot and bot_settings.

        Returns:
            Timezone-aware UTC datetime of latest snapshot, or None if no data exists.
        """
        async with self.session_factory() as session:
            # 1. From BillingSnapshot
            res = await session.execute(select(func.max(BillingSnapshot.recorded_at)))
            db_max = res.scalar()

            # 2. From bot_settings key 'last_poll_billing_at'
            setting_val = await get_bot_setting(session, "last_poll_billing_at")
            setting_dt: Optional[datetime] = None
            if setting_val:
                try:
                    setting_dt = datetime.fromisoformat(setting_val)
                except ValueError:
                    pass

            candidates: list[datetime] = []
            for dt in (db_max, setting_dt):
                if dt is not None:
                    ensured = _ensure_utc(dt)
                    if ensured is not None:
                        candidates.append(ensured)
            return max(candidates) if candidates else None

    async def check_and_sync_on_startup(self) -> Dict[str, Any]:
        """Evaluate database data freshness on startup and immediately poll if empty or stale.

        If data in database is missing or was updated longer ago than the active interval,
        triggers an immediate catch-up polling cycle. If data is still fresh, immediate
        polling is skipped.

        Returns:
            Dict summarizing evaluation results and actions taken:
            {
                "metrics": {"stale_or_empty": bool, "last_updated": datetime | None, "polled": bool},
                "billing": {"stale_or_empty": bool, "last_updated": datetime | None, "polled": bool},
            }
        """
        now = datetime.now(timezone.utc)
        metrics_last = await self.get_latest_metrics_timestamp()
        billing_last = await self.get_latest_billing_timestamp()

        # 1. Evaluate compute metrics freshness
        metrics_interval_delta = timedelta(minutes=self.current_metrics_interval)
        metrics_stale = False
        if metrics_last is None:
            logger.info("Database has no compute/metrics data. Immediate catch-up poll required.")
            metrics_stale = True
        else:
            elapsed_m = now - metrics_last
            if elapsed_m >= metrics_interval_delta:
                logger.info(
                    "Compute/metrics data is stale (last updated %s ago, interval %dm). Immediate catch-up poll required.",
                    elapsed_m,
                    self.current_metrics_interval,
                )
                metrics_stale = True
            else:
                logger.info(
                    "Compute/metrics data is fresh (last updated %s ago, interval %dm). Skipping immediate poll.",
                    elapsed_m,
                    self.current_metrics_interval,
                )

        # 2. Evaluate billing freshness
        billing_interval_delta = timedelta(hours=self.current_billing_interval)
        billing_stale = False
        if billing_last is None:
            logger.info("Database has no billing snapshot data. Immediate catch-up poll required.")
            billing_stale = True
        else:
            elapsed_b = now - billing_last
            if elapsed_b >= billing_interval_delta:
                logger.info(
                    "Billing data is stale (last updated %s ago, interval %dh). Immediate catch-up poll required.",
                    elapsed_b,
                    self.current_billing_interval,
                )
                billing_stale = True
            else:
                logger.info(
                    "Billing data is fresh (last updated %s ago, interval %dh). Skipping immediate poll.",
                    elapsed_b,
                    self.current_billing_interval,
                )

        # 3. Execute catch-up tasks in parallel if needed
        tasks = []
        if metrics_stale:
            tasks.append(self.trigger_metrics_poll())
        if billing_stale:
            tasks.append(self.trigger_billing_poll())

        if tasks:
            logger.info("Executing startup catch-up sync (%d task(s) in parallel)...", len(tasks))
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("Startup catch-up sync completed successfully.")

        return {
            "metrics": {
                "stale_or_empty": metrics_stale,
                "last_updated": metrics_last,
                "polled": metrics_stale,
            },
            "billing": {
                "stale_or_empty": billing_stale,
                "last_updated": billing_last,
                "polled": billing_stale,
            },
        }

    def get_status(self) -> Dict[str, Any]:
        """Return operational status and next run times for all scheduled jobs."""
        metrics_job = self.scheduler.get_job(self.JOB_ID_METRICS)
        billing_job = self.scheduler.get_job(self.JOB_ID_BILLING)

        return {
            "is_running": self.scheduler.running,
            "metrics_interval_minutes": self.current_metrics_interval,
            "billing_interval_hours": self.current_billing_interval,
            "metrics_next_run": metrics_job.next_run_time if metrics_job else None,
            "billing_next_run": billing_job.next_run_time if billing_job else None,
        }

    def shutdown(self, wait: bool = False) -> None:
        """Gracefully shutdown the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
            logger.info("Scheduler successfully shut down.")
