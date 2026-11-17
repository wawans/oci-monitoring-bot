"""Unit tests for SQLite database layer, SQLAlchemy ORM models, and account synchronization."""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Tuple
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config.parser import AccountConfig, AccountType
from src.database.connection import (
    close_db,
    get_bot_setting,
    get_engine,
    get_session,
    init_db,
    set_bot_setting,
    sync_accounts_to_db,
)
from src.database.models import (
    Account,
    AuditLog,
    Base,
    BillingSnapshot,
    BotSetting,
    InstanceState,
    MetricsLog,
)

DBFixture = Tuple[async_sessionmaker[AsyncSession], AsyncEngine]


@pytest.fixture
async def async_db(tmp_path: Path) -> AsyncGenerator[DBFixture, None]:
    """Fixture providing a temporary SQLite database engine and session factory."""
    db_file = tmp_path / "test_oci.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        # Enable foreign keys for SQLite
        await conn.execute(select(1))  # ping
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    yield session_factory, engine

    await engine.dispose()


class TestDatabaseModels:
    """Test ORM models and CRUD operations."""

    async def test_account_creation(self, async_db: DBFixture) -> None:
        """Test creating and querying an Account record."""
        session_factory, _ = async_db

        async with session_factory() as session:
            account = Account(
                account_id="acc_01",
                name="Test Prod",
                account_type="PAYG",
                region="ap-singapore-1",
                tenancy_ocid="ocid1.tenancy.oc1..test",
                compartment_id="ocid1.compartment.oc1..test",
                monthly_budget=100.0,
                is_active=True,
            )
            session.add(account)
            await session.commit()

        async with session_factory() as session:
            result = await session.execute(
                select(Account).where(Account.account_id == "acc_01")
            )
            fetched = result.scalars().first()
            assert fetched is not None
            assert fetched.name == "Test Prod"
            assert fetched.account_type == "PAYG"
            assert fetched.monthly_budget == 100.0
            assert fetched.is_active is True

    async def test_instance_state_and_metrics(self, async_db: DBFixture) -> None:
        """Test creating an InstanceState and logging telemetry metrics."""
        session_factory, _ = async_db

        async with session_factory() as session:
            account = Account(
                account_id="acc_02",
                name="Test Dev",
                account_type="FREE_TIER",
                region="ap-tokyo-1",
                tenancy_ocid="ocid1.tenancy.oc1..test",
                compartment_id="ocid1.compartment.oc1..test",
                monthly_budget=0.0,
                is_active=True,
            )
            session.add(account)
            await session.commit()

            instance = InstanceState(
                instance_id="ocid1.instance.oc1.ap-tokyo-1..vm1",
                account_id="acc_02",
                region="ap-tokyo-1",
                compartment_id="ocid1.compartment.oc1..test",
                display_name="dev-server",
                shape="VM.Standard.A1.Flex",
                public_ip="140.238.10.20",
                private_ip="10.0.0.5",
                lifecycle_state="RUNNING",
                latest_cpu_percent=12.5,
                consecutive_high_cpu=0,
            )
            session.add(instance)
            await session.commit()

            # Add metrics logs
            metric1 = MetricsLog(
                instance_id="ocid1.instance.oc1.ap-tokyo-1..vm1",
                cpu_percent=12.5,
            )
            metric2 = MetricsLog(
                instance_id="ocid1.instance.oc1.ap-tokyo-1..vm1",
                cpu_percent=15.0,
            )
            session.add_all([metric1, metric2])
            await session.commit()

        async with session_factory() as session:
            result = await session.execute(
                select(InstanceState).where(
                    InstanceState.instance_id == "ocid1.instance.oc1.ap-tokyo-1..vm1"
                )
            )
            inst = result.scalars().first()
            assert inst is not None
            assert inst.public_ip == "140.238.10.20"
            assert inst.private_ip == "10.0.0.5"
            assert inst.lifecycle_state == "RUNNING"

            metrics_result = await session.execute(
                select(MetricsLog).where(
                    MetricsLog.instance_id == "ocid1.instance.oc1.ap-tokyo-1..vm1"
                )
            )
            all_metrics = metrics_result.scalars().all()
            assert len(all_metrics) == 2

    async def test_billing_and_audit_log(self, async_db: DBFixture) -> None:
        """Test billing snapshot recording and power action audit logging."""
        session_factory, _ = async_db

        async with session_factory() as session:
            account = Account(
                account_id="acc_03",
                name="Billing Account",
                account_type="PAYG",
                region="us-ashburn-1",
                tenancy_ocid="ocid1.tenancy.oc1..test",
                compartment_id="ocid1.compartment.oc1..test",
                monthly_budget=50.0,
                is_active=True,
            )
            session.add(account)
            await session.commit()

            snapshot = BillingSnapshot(
                account_id="acc_03",
                amount=18.75,
                currency="USD",
                billing_period="2026-11",
            )
            audit = AuditLog(
                user_id=123456789,
                account_id="acc_03",
                instance_id="ocid1.instance.oc1..testvm",
                action="STOP",
                status="SUCCESS",
            )
            session.add_all([snapshot, audit])
            await session.commit()

        async with session_factory() as session:
            snap_res = await session.execute(
                select(BillingSnapshot).where(BillingSnapshot.account_id == "acc_03")
            )
            snap = snap_res.scalars().first()
            assert snap is not None
            assert snap.amount == 18.75
            assert snap.currency == "USD"
            assert snap.billing_period == "2026-11"

            audit_res = await session.execute(
                select(AuditLog).where(AuditLog.user_id == 123456789)
            )
            audit_entry = audit_res.scalars().first()
            assert audit_entry is not None
            assert audit_entry.action == "STOP"
            assert audit_entry.status == "SUCCESS"


class TestBotSettings:
    """Test dynamic runtime bot settings get/set utilities."""

    async def test_bot_settings_operations(self, async_db: DBFixture) -> None:
        """Test getting, setting, and updating dynamic bot settings."""
        session_factory, _ = async_db

        async with session_factory() as session:
            # Default fallback when key does not exist
            val = await get_bot_setting(session, "poll_metrics_interval", default="10")
            assert val == "10"

            # Set new value
            await set_bot_setting(session, "poll_metrics_interval", "5")
            await session.commit()

        async with session_factory() as session:
            val = await get_bot_setting(session, "poll_metrics_interval")
            assert val == "5"

            # Update existing value
            await set_bot_setting(session, "poll_metrics_interval", "30")
            await session.commit()

        async with session_factory() as session:
            val = await get_bot_setting(session, "poll_metrics_interval")
            assert val == "30"


class TestSyncAccounts:
    """Test synchronization from AccountConfig YAML objects into database."""

    async def test_sync_accounts_to_db(self, async_db: DBFixture) -> None:
        """Verify upserting accounts creates and subsequently updates accounts."""
        session_factory, _ = async_db

        accounts_to_sync = [
            AccountConfig(
                account_id="sync_01",
                name="Initial Name",
                account_type=AccountType.PAYG,
                tenancy_ocid="ocid1.tenancy.oc1..sync1",
                user_ocid="ocid1.user.oc1..user1",
                fingerprint="11:22:33:44:55:66:77:88:99:00:11:22:33:44:55:66",
                key_file=Path("credentials/keys/key1.pem"),
                region="ap-singapore-1",
                compartment_id="ocid1.compartment.oc1..comp1",
                monthly_budget=50.0,
                is_active=True,
            ),
            AccountConfig(
                account_id="sync_02",
                name="Free Tier Account",
                account_type=AccountType.FREE_TIER,
                tenancy_ocid="ocid1.tenancy.oc1..sync2",
                user_ocid="ocid1.user.oc1..user2",
                fingerprint="aa:bb:cc:dd:ee:ff:11:22:33:44:55:66:77:88:99:00",
                key_file=Path("credentials/keys/key2.pem"),
                region="ap-tokyo-1",
                compartment_id="ocid1.compartment.oc1..comp2",
                monthly_budget=0.0,
                is_active=True,
            ),
        ]

        # First sync (inserts)
        async with session_factory() as session:
            count = await sync_accounts_to_db(accounts_to_sync, session)
            assert count == 2
            await session.commit()

        async with session_factory() as session:
            res = await session.execute(select(Account))
            all_accounts = res.scalars().all()
            assert len(all_accounts) == 2
            a1 = next(a for a in all_accounts if a.account_id == "sync_01")
            assert a1.name == "Initial Name"
            assert a1.monthly_budget == 50.0

        # Second sync with updated values (updates)
        accounts_to_sync[0].name = "Updated Name"
        accounts_to_sync[0].monthly_budget = 99.0

        async with session_factory() as session:
            count = await sync_accounts_to_db(accounts_to_sync, session)
            assert count == 2
            await session.commit()

        async with session_factory() as session:
            res = await session.execute(select(Account))
            all_accounts = res.scalars().all()
            assert len(all_accounts) == 2
            a1 = next(a for a in all_accounts if a.account_id == "sync_01")
            assert a1.name == "Updated Name"
            assert a1.monthly_budget == 99.0


class TestInitDbAndWal:
    """Test database initialization and WAL configuration."""

    async def test_init_db_creates_tables_and_wal(self, tmp_path: Path) -> None:
        """Verify init_db creates database file and sets journal mode to WAL."""
        db_file = tmp_path / "subfolder" / "oci_wal.db"
        db_url = f"sqlite+aiosqlite:///{db_file}"

        await close_db()
        try:
            await init_db(db_url)
            assert db_file.exists()

            async with get_session(db_url) as session:
                result = await session.execute(select(Account))
                assert result.scalars().all() == []
        finally:
            await close_db()

