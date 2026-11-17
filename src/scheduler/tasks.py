"""Background polling tasks and state difference engine."""

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.database.models import BillingSnapshot, InstanceState, MetricsLog
from src.oci_services.billing import BillingService
from src.oci_services.client_factory import OCIClientFactory
from src.oci_services.compute import ComputeService
from src.oci_services.monitoring import MonitoringService
from src.scheduler.detector import IncidentAlert, IncidentDetector

logger = logging.getLogger(__name__)

AlertCallback = Callable[[IncidentAlert], Awaitable[None]]


async def poll_metrics_task(
    client_factory: OCIClientFactory,
    compute_service: ComputeService,
    monitoring_service: MonitoringService,
    session_factory: async_sessionmaker[AsyncSession],
    alert_callback: Optional[AlertCallback] = None,
) -> int:
    """Poll compute instances and CPU telemetry across all active accounts.

    Applies per-account fault isolation: failure on Account A does not stop Account B.
    Updates SQLite database cache and dispatches push alerts ONLY when anomalies occur.

    Returns:
        Total number of compute instances evaluated across all accounts.
    """
    bundles = client_factory.get_all_bundles()
    total_evaluated = 0

    for bundle in bundles:
        try:
            logger.debug(
                "Polling compute and metrics for account %s (%s)...",
                bundle.account_id,
                bundle.account_name,
            )
            instances = await compute_service.list_instances(bundle, resolve_ips=True)

            async with session_factory() as session:
                for inst in instances:
                    total_evaluated += 1
                    cpu = await monitoring_service.get_latest_cpu_utilization(
                        bundle, inst.instance_id
                    )

                    result = await session.execute(
                        select(InstanceState).where(
                            InstanceState.instance_id == inst.instance_id
                        )
                    )
                    db_instance = result.scalars().first()
                    now = datetime.now(timezone.utc)

                    if db_instance:
                        # 1. State transition detection
                        state_alert = IncidentDetector.check_state_transition(
                            account_id=bundle.account_id,
                            account_name=bundle.account_name,
                            instance_id=inst.instance_id,
                            instance_name=inst.display_name,
                            previous_state=db_instance.lifecycle_state,
                            current_state=inst.lifecycle_state,
                        )
                        if state_alert and alert_callback:
                            try:
                                await alert_callback(state_alert)
                            except Exception as alert_err:
                                logger.error("Failed to deliver state alert: %s", alert_err)

                        # 2. CPU spike detection
                        consecutive, cpu_alert = IncidentDetector.check_cpu_utilization(
                            account_id=bundle.account_id,
                            account_name=bundle.account_name,
                            instance_id=inst.instance_id,
                            instance_name=inst.display_name,
                            cpu_percent=cpu,
                            previous_consecutive_high=db_instance.consecutive_high_cpu,
                        )
                        if cpu_alert and alert_callback:
                            try:
                                await alert_callback(cpu_alert)
                            except Exception as alert_err:
                                logger.error("Failed to deliver CPU alert: %s", alert_err)

                        # Update existing DB record
                        db_instance.display_name = inst.display_name
                        db_instance.shape = inst.shape
                        db_instance.lifecycle_state = inst.lifecycle_state
                        if inst.public_ip:
                            db_instance.public_ip = inst.public_ip
                        if inst.private_ip:
                            db_instance.private_ip = inst.private_ip
                        db_instance.latest_cpu_percent = cpu
                        db_instance.consecutive_high_cpu = consecutive
                        db_instance.last_seen = now

                    else:
                        # First time registration in database
                        init_consecutive = 1 if (cpu and cpu > IncidentDetector.CPU_THRESHOLD_PERCENT) else 0
                        new_record = InstanceState(
                            instance_id=inst.instance_id,
                            account_id=bundle.account_id,
                            region=bundle.region,
                            compartment_id=bundle.compartment_id,
                            display_name=inst.display_name,
                            shape=inst.shape,
                            public_ip=inst.public_ip,
                            private_ip=inst.private_ip,
                            lifecycle_state=inst.lifecycle_state,
                            latest_cpu_percent=cpu,
                            consecutive_high_cpu=init_consecutive,
                            last_seen=now,
                        )
                        session.add(new_record)

                    # Record telemetry log if CPU metric is available
                    if cpu is not None:
                        metric_entry = MetricsLog(
                            instance_id=inst.instance_id,
                            cpu_percent=cpu,
                            timestamp=now,
                        )
                        session.add(metric_entry)

                await session.commit()

        except Exception as e:
            # Fault isolation: log and continue to remaining accounts
            logger.error(
                "Polling error for account %s (%s): %s",
                bundle.account_id,
                bundle.account_name,
                e,
            )

    logger.debug("Metrics poll cycle completed. Evaluated %d instances.", total_evaluated)
    return total_evaluated


async def poll_billing_task(
    client_factory: OCIClientFactory,
    billing_service: BillingService,
    session_factory: async_sessionmaker[AsyncSession],
    alert_callback: Optional[AlertCallback] = None,
) -> int:
    """Poll billing MTD summaries and run-rate forecast across all active accounts.

    Applies per-account fault isolation.
    Records billing snapshots and dispatches alerts if monthly budgets are breached.

    Returns:
        Number of accounts successfully polled.
    """
    bundles = client_factory.get_all_bundles()
    polled_count = 0

    for bundle in bundles:
        try:
            logger.debug(
                "Polling billing for account %s (%s)...",
                bundle.account_id,
                bundle.account_name,
            )
            summary = await billing_service.get_billing_summary(bundle)

            # Record snapshot in SQLite
            async with session_factory() as session:
                snapshot = BillingSnapshot(
                    account_id=bundle.account_id,
                    amount=summary.mtd_spend,
                    currency=summary.currency,
                    billing_period=summary.billing_period,
                    recorded_at=summary.recorded_at,
                )
                session.add(snapshot)
                await session.commit()

            polled_count += 1

            # Check budget alert
            budget_alert = IncidentDetector.check_budget_limit(
                account_id=bundle.account_id,
                account_name=bundle.account_name,
                forecast_spend=summary.forecast_spend,
                monthly_budget=bundle.monthly_budget,
                currency=summary.currency,
            )
            if budget_alert and alert_callback:
                try:
                    await alert_callback(budget_alert)
                except Exception as alert_err:
                    logger.error("Failed to deliver budget alert: %s", alert_err)

        except Exception as e:
            # Fault isolation
            logger.error(
                "Billing poll error for account %s (%s): %s",
                bundle.account_id,
                bundle.account_name,
                e,
            )

    logger.debug("Billing poll cycle completed. Polled %d accounts.", polled_count)
    return polled_count
