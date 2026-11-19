"""Unit tests for background scheduler manager and polling tasks."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Tuple
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config.parser import AccountType
from src.database.models import Account, Base, BillingSnapshot, InstanceState
from src.oci_services.billing import BillingSummary
from src.oci_services.client_factory import OCIClientBundle
from src.oci_services.compute import InstanceInfo
from src.scheduler.detector import IncidentAlert, IncidentType
from src.scheduler.manager import SchedulerManager
from src.scheduler.tasks import poll_billing_task, poll_metrics_task

SchedDBFixture = Tuple[async_sessionmaker[AsyncSession], AsyncEngine]


@pytest.fixture
async def scheduler_db(tmp_path: Path) -> AsyncGenerator[SchedDBFixture, None]:
    """Fixture providing a temporary SQLite database engine and session factory."""
    db_file = tmp_path / "test_scheduler.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Insert test account
    async with session_factory() as session:
        acc = Account(
            account_id="acc_sched_test",
            name="Sched Test Account",
            account_type="PAYG",
            region="ap-singapore-1",
            tenancy_ocid="ocid1.tenancy.oc1..test",
            compartment_id="ocid1.compartment.oc1..test",
            monthly_budget=50.0,
            is_active=True,
        )
        session.add(acc)
        await session.commit()

    yield session_factory, engine

    await engine.dispose()


class TestSchedulerManager:
    """Tests for scheduler lifecycle, job registration, and dynamic rescheduling."""

    async def test_manager_lifecycle_and_reschedule(self) -> None:
        """Test starting, rescheduling jobs, and shutting down SchedulerManager."""
        mock_factory = MagicMock()
        mock_compute = MagicMock()
        mock_monitoring = MagicMock()
        mock_billing = MagicMock()
        mock_session_factory = MagicMock()

        mgr = SchedulerManager(
            client_factory=mock_factory,
            compute_service=mock_compute,
            monitoring_service=mock_monitoring,
            billing_service=mock_billing,
            session_factory=mock_session_factory,
        )

        try:
            # Start scheduler with 10m metrics, 6h billing
            mgr.start(metrics_interval_minutes=10, billing_interval_hours=6)
            status = mgr.get_status()
            assert status["is_running"] is True
            assert status["metrics_interval_minutes"] == 10
            assert status["billing_interval_hours"] == 6

            # Dynamically reschedule metrics to 30m
            rescheduled = mgr.reschedule_metrics(30)
            assert rescheduled is True
            assert mgr.current_metrics_interval == 30

            # Dynamically reschedule billing to 12h
            rescheduled_b = mgr.reschedule_billing(12)
            assert rescheduled_b is True
            assert mgr.current_billing_interval == 12

        finally:
            mgr.shutdown(wait=False)
            await asyncio.sleep(0.01)
            assert mgr.scheduler.running is False

    async def test_startup_sync_empty_database_triggers_both(
        self, scheduler_db: SchedDBFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When database is empty, startup sync should trigger both metrics and billing polls."""
        session_factory, _ = scheduler_db

        mock_factory = MagicMock()
        mock_compute = MagicMock()
        mock_monitoring = MagicMock()
        mock_billing = MagicMock()

        mgr = SchedulerManager(
            client_factory=mock_factory,
            compute_service=mock_compute,
            monitoring_service=mock_monitoring,
            billing_service=mock_billing,
            session_factory=session_factory,
        )

        mock_poll_m = AsyncMock(return_value=1)
        mock_poll_b = AsyncMock(return_value=1)
        monkeypatch.setattr(mgr, "trigger_metrics_poll", mock_poll_m)
        monkeypatch.setattr(mgr, "trigger_billing_poll", mock_poll_b)

        result = await mgr.check_and_sync_on_startup()

        assert result["metrics"]["stale_or_empty"] is True
        assert result["metrics"]["polled"] is True
        assert result["billing"]["stale_or_empty"] is True
        assert result["billing"]["polled"] is True

        mock_poll_m.assert_awaited_once()
        mock_poll_b.assert_awaited_once()

    async def test_startup_sync_stale_metrics_triggers_metrics_only(
        self, scheduler_db: SchedDBFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When metrics data is older than interval but billing is fresh, only metrics is polled."""
        session_factory, _ = scheduler_db
        now = datetime.now(timezone.utc)

        # Stale metrics (2h old vs 10m interval) and fresh billing (30m old vs 6h interval)
        async with session_factory() as session:
            stale_inst = InstanceState(
                instance_id="ocid1.instance.oc1..stale",
                account_id="acc_sched_test",
                region="ap-singapore-1",
                compartment_id="ocid1.compartment.oc1..test",
                display_name="stale-vm",
                shape="VM.Standard.E4.Flex",
                lifecycle_state="RUNNING",
                last_seen=now - timedelta(hours=2),
            )
            session.add(stale_inst)

            fresh_snap = BillingSnapshot(
                account_id="acc_sched_test",
                amount=15.0,
                currency="USD",
                billing_period="2026-11",
                recorded_at=now - timedelta(minutes=30),
            )
            session.add(fresh_snap)
            await session.commit()

        mock_factory = MagicMock()
        mock_compute = MagicMock()
        mock_monitoring = MagicMock()
        mock_billing = MagicMock()

        mgr = SchedulerManager(
            client_factory=mock_factory,
            compute_service=mock_compute,
            monitoring_service=mock_monitoring,
            billing_service=mock_billing,
            session_factory=session_factory,
        )
        mgr.current_metrics_interval = 10
        mgr.current_billing_interval = 6

        mock_poll_m = AsyncMock(return_value=1)
        mock_poll_b = AsyncMock(return_value=1)
        monkeypatch.setattr(mgr, "trigger_metrics_poll", mock_poll_m)
        monkeypatch.setattr(mgr, "trigger_billing_poll", mock_poll_b)

        result = await mgr.check_and_sync_on_startup()

        assert result["metrics"]["stale_or_empty"] is True
        assert result["metrics"]["polled"] is True
        assert result["billing"]["stale_or_empty"] is False
        assert result["billing"]["polled"] is False

        mock_poll_m.assert_awaited_once()
        mock_poll_b.assert_not_awaited()

    async def test_startup_sync_fresh_data_skips_both(
        self, scheduler_db: SchedDBFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When both metrics and billing data are fresh, startup catch-up is skipped."""
        session_factory, _ = scheduler_db
        now = datetime.now(timezone.utc)

        async with session_factory() as session:
            fresh_inst = InstanceState(
                instance_id="ocid1.instance.oc1..fresh",
                account_id="acc_sched_test",
                region="ap-singapore-1",
                compartment_id="ocid1.compartment.oc1..test",
                display_name="fresh-vm",
                shape="VM.Standard.E4.Flex",
                lifecycle_state="RUNNING",
                last_seen=now - timedelta(minutes=2),
            )
            session.add(fresh_inst)

            fresh_snap = BillingSnapshot(
                account_id="acc_sched_test",
                amount=15.0,
                currency="USD",
                billing_period="2026-11",
                recorded_at=now - timedelta(hours=1),
            )
            session.add(fresh_snap)
            await session.commit()

        mock_factory = MagicMock()
        mock_compute = MagicMock()
        mock_monitoring = MagicMock()
        mock_billing = MagicMock()

        mgr = SchedulerManager(
            client_factory=mock_factory,
            compute_service=mock_compute,
            monitoring_service=mock_monitoring,
            billing_service=mock_billing,
            session_factory=session_factory,
        )
        mgr.current_metrics_interval = 10
        mgr.current_billing_interval = 6

        mock_poll_m = AsyncMock(return_value=1)
        mock_poll_b = AsyncMock(return_value=1)
        monkeypatch.setattr(mgr, "trigger_metrics_poll", mock_poll_m)
        monkeypatch.setattr(mgr, "trigger_billing_poll", mock_poll_b)

        result = await mgr.check_and_sync_on_startup()

        assert result["metrics"]["stale_or_empty"] is False
        assert result["metrics"]["polled"] is False
        assert result["billing"]["stale_or_empty"] is False
        assert result["billing"]["polled"] is False

        mock_poll_m.assert_not_awaited()
        mock_poll_b.assert_not_awaited()

    async def test_startup_sync_naive_timezone_safe(
        self, scheduler_db: SchedDBFixture
    ) -> None:
        """Verify that offset-naive datetimes from SQLite are safely handled without TypeError."""
        session_factory, _ = scheduler_db
        naive_dt = datetime.now() - timedelta(minutes=3)

        async with session_factory() as session:
            naive_inst = InstanceState(
                instance_id="ocid1.instance.oc1..naive",
                account_id="acc_sched_test",
                region="ap-singapore-1",
                compartment_id="ocid1.compartment.oc1..test",
                display_name="naive-vm",
                shape="VM.Standard.E4.Flex",
                lifecycle_state="RUNNING",
                last_seen=naive_dt,
            )
            session.add(naive_inst)
            await session.commit()

        mgr = SchedulerManager(
            client_factory=MagicMock(),
            compute_service=MagicMock(),
            monitoring_service=MagicMock(),
            billing_service=MagicMock(),
            session_factory=session_factory,
        )
        latest = await mgr.get_latest_metrics_timestamp()
        assert latest is not None
        assert latest.tzinfo == timezone.utc


class TestSchedulerTasks:
    """Tests for periodic metrics and billing polling tasks with silent watchdog."""

    async def test_poll_metrics_initial_and_state_change(
        self, scheduler_db: SchedDBFixture
    ) -> None:
        """Test initial metrics population and subsequent state outage detection."""
        session_factory, _ = scheduler_db

        mock_bundle = MagicMock(spec=OCIClientBundle)
        mock_bundle.account_id = "acc_sched_test"
        mock_bundle.account_name = "Sched Test Account"
        mock_bundle.region = "ap-singapore-1"
        mock_bundle.compartment_id = "ocid1.compartment.oc1..test"

        mock_factory = MagicMock()
        mock_factory.get_all_bundles.return_value = [mock_bundle]

        mock_compute = MagicMock()
        mock_monitoring = MagicMock()

        # Cycle 1: Instance is RUNNING
        inst1 = InstanceInfo(
            instance_id="ocid1.instance.oc1..vm1",
            account_id="acc_sched_test",
            region="ap-singapore-1",
            compartment_id="ocid1.compartment.oc1..test",
            display_name="prod-web",
            shape="VM.Standard.A1.Flex",
            lifecycle_state="RUNNING",
            public_ip="140.238.1.1",
            private_ip="10.0.0.2",
        )
        mock_compute.list_instances = AsyncMock(return_value=[inst1])
        mock_monitoring.get_latest_cpu_utilization = AsyncMock(return_value=25.0)

        alert_callback = AsyncMock()

        # Run Cycle 1
        count = await poll_metrics_task(
            mock_factory,
            mock_compute,
            mock_monitoring,
            session_factory,
            alert_callback=alert_callback,
        )
        assert count == 1
        alert_callback.assert_not_called()  # Silent on initial run!

        # Verify DB entry
        async with session_factory() as session:
            res = await session.execute(
                select(InstanceState).where(
                    InstanceState.instance_id == "ocid1.instance.oc1..vm1"
                )
            )
            saved_vm = res.scalars().first()
            assert saved_vm is not None
            assert saved_vm.lifecycle_state == "RUNNING"
            assert saved_vm.latest_cpu_percent == 25.0

        # Cycle 2: Instance unexpectedly crashes to STOPPED
        inst1_stopped = InstanceInfo(
            instance_id="ocid1.instance.oc1..vm1",
            account_id="acc_sched_test",
            region="ap-singapore-1",
            compartment_id="ocid1.compartment.oc1..test",
            display_name="prod-web",
            shape="VM.Standard.A1.Flex",
            lifecycle_state="STOPPED",
            public_ip="140.238.1.1",
            private_ip="10.0.0.2",
        )
        mock_compute.list_instances = AsyncMock(return_value=[inst1_stopped])
        mock_monitoring.get_latest_cpu_utilization = AsyncMock(return_value=None)

        # Run Cycle 2
        await poll_metrics_task(
            mock_factory,
            mock_compute,
            mock_monitoring,
            session_factory,
            alert_callback=alert_callback,
        )

        # Alert must have been fired!
        alert_callback.assert_called_once()
        alert: IncidentAlert = alert_callback.call_args[0][0]
        assert alert.incident_type == IncidentType.VM_DOWN
        assert alert.instance_name == "prod-web"

    async def test_poll_metrics_cpu_spike_two_cycles(
        self, scheduler_db: SchedDBFixture
    ) -> None:
        """Verify CPU spike triggers alert only on second consecutive cycle."""
        session_factory, _ = scheduler_db

        mock_bundle = MagicMock(spec=OCIClientBundle)
        mock_bundle.account_id = "acc_sched_test"
        mock_bundle.account_name = "Sched Test Account"
        mock_bundle.region = "ap-singapore-1"
        mock_bundle.compartment_id = "ocid1.compartment.oc1..test"

        mock_factory = MagicMock()
        mock_factory.get_all_bundles.return_value = [mock_bundle]

        mock_compute = MagicMock()
        mock_monitoring = MagicMock()

        inst = InstanceInfo(
            instance_id="ocid1.instance.oc1..vm_cpu",
            account_id="acc_sched_test",
            region="ap-singapore-1",
            compartment_id="ocid1.compartment.oc1..test",
            display_name="worker-01",
            shape="VM.Standard.A1.Flex",
            lifecycle_state="RUNNING",
        )
        mock_compute.list_instances = AsyncMock(return_value=[inst])
        alert_callback = AsyncMock()

        # Cycle 1: CPU = 95%
        mock_monitoring.get_latest_cpu_utilization = AsyncMock(return_value=95.0)
        await poll_metrics_task(
            mock_factory,
            mock_compute,
            mock_monitoring,
            session_factory,
            alert_callback=alert_callback,
        )
        alert_callback.assert_not_called()  # Silent on first high cycle!

        # Cycle 2: CPU = 96%
        mock_monitoring.get_latest_cpu_utilization = AsyncMock(return_value=96.0)
        await poll_metrics_task(
            mock_factory,
            mock_compute,
            mock_monitoring,
            session_factory,
            alert_callback=alert_callback,
        )
        alert_callback.assert_called_once()  # Fired on second consecutive cycle!
        alert: IncidentAlert = alert_callback.call_args[0][0]
        assert alert.incident_type == IncidentType.HIGH_CPU_SPIKE

    async def test_poll_billing_task(self, scheduler_db: SchedDBFixture) -> None:
        """Test periodic billing poll, database snapshot creation, and budget alerts."""
        session_factory, _ = scheduler_db

        mock_bundle = MagicMock(spec=OCIClientBundle)
        mock_bundle.account_id = "acc_sched_test"
        mock_bundle.account_name = "Sched Test Account"
        mock_bundle.monthly_budget = 50.0

        mock_factory = MagicMock()
        mock_factory.get_all_bundles.return_value = [mock_bundle]

        mock_billing = MagicMock()
        summary = BillingSummary(
            account_id="acc_sched_test",
            account_name="Sched Test Account",
            account_type=AccountType.PAYG,
            mtd_spend=30.0,
            forecast_spend=90.0,  # Exceeds budget 50.0
            monthly_budget=50.0,
            currency="USD",
            billing_period="2026-11",
            is_budget_exceeded=True,
            recorded_at=datetime.now(timezone.utc),
        )
        mock_billing.get_billing_summary = AsyncMock(return_value=summary)

        alert_callback = AsyncMock()

        count = await poll_billing_task(
            mock_factory,
            mock_billing,
            session_factory,
            alert_callback=alert_callback,
        )
        assert count == 1

        # Verify snapshot recorded in SQLite
        async with session_factory() as session:
            res = await session.execute(
                select(BillingSnapshot).where(
                    BillingSnapshot.account_id == "acc_sched_test"
                )
            )
            snapshot = res.scalars().first()
            assert snapshot is not None
            assert snapshot.amount == 30.0
            assert snapshot.currency == "USD"

        # Verify budget alert dispatched
        alert_callback.assert_called_once()
        alert: IncidentAlert = alert_callback.call_args[0][0]
        assert alert.incident_type == IncidentType.BUDGET_EXCEEDED
        assert alert.metric_value == 90.0
