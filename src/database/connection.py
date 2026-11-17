"""Database engine, session management, and synchronization functions."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config.parser import AccountConfig
from config.settings import get_settings
from src.database.models import Account, Base, BotSetting

logger = logging.getLogger(__name__)

# Global engine and sessionmaker singletons
_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine(database_url: Optional[str] = None) -> AsyncEngine:
    """Get or create singleton async SQLAlchemy engine with SQLite WAL mode."""
    global _engine, _sessionmaker

    target_url = database_url if database_url is not None else get_settings().database_url

    if _engine is None:
        # Ensure directory exists if SQLite file path is provided
        if "sqlite" in target_url and "///" in target_url:
            db_path_str = target_url.split("///")[-1]
            if db_path_str and not db_path_str.startswith(":memory:"):
                db_path = Path(db_path_str)
                db_path.parent.mkdir(parents=True, exist_ok=True)

        _engine = create_async_engine(
            target_url,
            echo=False,
            future=True,
        )

        # Configure SQLite pragmas for performance and concurrency
        if "sqlite" in target_url:
            @event.listens_for(_engine.sync_engine, "connect")
            def _set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
                cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
                try:
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA synchronous=NORMAL")
                    cursor.execute("PRAGMA busy_timeout=5000")
                    cursor.execute("PRAGMA foreign_keys=ON")
                finally:
                    cursor.close()

        _sessionmaker = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info("Initialized async database engine for URL: %s", target_url)

    return _engine


def get_session_factory(database_url: Optional[str] = None) -> async_sessionmaker[AsyncSession]:
    """Return configured async session factory."""
    global _sessionmaker
    if _sessionmaker is None:
        get_engine(database_url)
    assert _sessionmaker is not None
    return _sessionmaker


@asynccontextmanager
async def get_session(database_url: Optional[str] = None) -> AsyncGenerator[AsyncSession, None]:
    """Async context manager providing an isolated AsyncSession with auto commit/rollback."""
    factory = get_session_factory(database_url)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db(database_url: Optional[str] = None) -> None:
    """Initialize database tables according to SQLAlchemy metadata."""
    engine = get_engine(database_url)
    logger.info("Creating database tables if not existing...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema initialized successfully.")


async def close_db() -> None:
    """Dispose of the active database engine connection pool."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
        logger.info("Database engine disposed.")


async def sync_accounts_to_db(
    accounts: List[AccountConfig],
    session: AsyncSession,
) -> int:
    """Synchronize list of AccountConfig objects into the ACCOUNTS table.

    Updates existing account rows or inserts new ones.

    Args:
        accounts: List of AccountConfig instances from accounts.yaml
        session: Active async SQLAlchemy session

    Returns:
        Number of accounts inserted or updated.
    """
    synced_count = 0

    for acc in accounts:
        result = await session.execute(
            select(Account).where(Account.account_id == acc.account_id)
        )
        existing_account = result.scalars().first()

        if existing_account:
            existing_account.name = acc.name
            existing_account.account_type = acc.account_type.value
            existing_account.region = acc.region
            existing_account.tenancy_ocid = acc.tenancy_ocid
            existing_account.compartment_id = acc.compartment_id
            existing_account.monthly_budget = acc.monthly_budget
            existing_account.is_active = acc.is_active
            logger.debug("Updated account in DB: %s (%s)", acc.account_id, acc.name)
        else:
            new_account = Account(
                account_id=acc.account_id,
                name=acc.name,
                account_type=acc.account_type.value,
                region=acc.region,
                tenancy_ocid=acc.tenancy_ocid,
                compartment_id=acc.compartment_id,
                monthly_budget=acc.monthly_budget,
                is_active=acc.is_active,
            )
            session.add(new_account)
            logger.debug("Inserted new account in DB: %s (%s)", acc.account_id, acc.name)

        synced_count += 1

    await session.flush()
    logger.info("Synchronized %d accounts to database.", synced_count)
    return synced_count


async def get_bot_setting(
    session: AsyncSession,
    key: str,
    default: Optional[str] = None,
) -> Optional[str]:
    """Retrieve dynamic bot setting value by key."""
    result = await session.execute(
        select(BotSetting.value).where(BotSetting.key == key)
    )
    val = result.scalars().first()
    return val if val is not None else default


async def set_bot_setting(
    session: AsyncSession,
    key: str,
    value: str,
) -> None:
    """Insert or update dynamic bot setting key-value pair."""
    result = await session.execute(
        select(BotSetting).where(BotSetting.key == key)
    )
    setting = result.scalars().first()
    if setting:
        setting.value = value
    else:
        session.add(BotSetting(key=key, value=value))
    await session.flush()
    logger.debug("Saved bot setting %s = %s", key, value)
