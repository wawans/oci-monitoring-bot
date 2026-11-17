"""Application settings management using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Optional, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration settings for the OCI Monitoring Bot."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram Bot Configuration
    telegram_bot_token: str = Field(
        default="",
        alias="TELEGRAM_BOT_TOKEN",
        description="Bot token obtained from Telegram @BotFather",
    )
    telegram_admin_user_id: int = Field(
        default=0,
        alias="TELEGRAM_ADMIN_USER_ID",
        description="Numeric Telegram User ID of authorized bot admin",
    )

    # Database Configuration
    database_url: str = Field(
        default="sqlite+aiosqlite:///data/oci_bot.db",
        alias="DATABASE_URL",
        description="Async SQLite database connection string",
    )

    # OCI Accounts Configuration
    accounts_config_path: Union[Path, str] = Field(
        default=Path("config/accounts.yaml"),
        alias="ACCOUNTS_CONFIG_PATH",
        description="Path to OCI accounts YAML configuration file",
    )

    # Logging Configuration
    log_level: str = Field(
        default="INFO",
        alias="LOG_LEVEL",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    # Polling Intervals
    default_metrics_interval_minutes: int = Field(
        default=10,
        alias="DEFAULT_METRICS_INTERVAL_MINUTES",
        description="Default interval for compute and CPU metrics polling in minutes",
    )
    default_billing_interval_hours: int = Field(
        default=6,
        alias="DEFAULT_BILLING_INTERVAL_HOURS",
        description="Default interval for billing and forecast polling in hours",
    )

    @field_validator("accounts_config_path", mode="after")
    @classmethod
    def parse_path(cls, v: Union[Path, str]) -> Path:
        """Convert string path to pathlib.Path object."""
        if isinstance(v, Path):
            return v
        return Path(str(v))

    @property
    def is_telegram_configured(self) -> bool:
        """Check whether Telegram bot credentials are fully provided."""
        return bool(self.telegram_bot_token and self.telegram_admin_user_id > 0)

    @property
    def resolved_database_path(self) -> Optional[Path]:
        """Extract Path to sqlite database file if using sqlite URI."""
        if "sqlite" in self.database_url:
            # Extract raw path after ':///'
            path_part = self.database_url.split(":///")[-1]
            return Path(path_part)
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached instance of application settings."""
    return Settings()
