"""Dynamic background scheduler manager with runtime rescheduling (ADR-006)."""

import logging
from typing import Any, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.scheduler.tasks import AlertCallback, poll_billing_task, poll_metrics_task

logger = logging.getLogger(__name__)


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
