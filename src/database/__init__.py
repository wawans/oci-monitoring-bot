"""Database package exposing models and connection utilities."""

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

__all__ = [
    "Account",
    "AuditLog",
    "Base",
    "BillingSnapshot",
    "BotSetting",
    "InstanceState",
    "MetricsLog",
    "close_db",
    "get_bot_setting",
    "get_engine",
    "get_session",
    "init_db",
    "set_bot_setting",
    "sync_accounts_to_db",
]
