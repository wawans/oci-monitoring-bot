"""OCI Multi-Account YAML configuration parser and validator."""

import logging
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class AccountType(str, Enum):
    """Supported OCI account types."""

    PAYG = "PAYG"
    FREE_TIER = "FREE_TIER"


class ConfigError(Exception):
    """Base exception for configuration-related errors."""


class AccountsFileNotFoundError(ConfigError):
    """Raised when accounts YAML file cannot be found."""


class InvalidAccountConfigError(ConfigError):
    """Raised when account YAML content is malformed or invalid."""


class KeyFileNotFoundError(ConfigError):
    """Raised when a specified .pem key file does not exist on disk."""


class AccountConfig(BaseModel):
    """Configuration model for an individual OCI account."""

    account_id: str = Field(..., min_length=1, max_length=64, description="Unique account identifier")
    name: str = Field(..., min_length=1, max_length=128, description="Display name for Telegram UI")
    account_type: AccountType = Field(default=AccountType.FREE_TIER, description="Account tier type")
    tenancy_ocid: str = Field(..., min_length=10, description="Tenancy OCID")
    user_ocid: str = Field(..., min_length=10, description="User OCID")
    fingerprint: str = Field(..., min_length=10, description="API Key fingerprint (xx:xx:xx...)")
    key_file: Path = Field(..., description="Path to private .pem key file")
    region: str = Field(..., min_length=2, description="OCI Region identifier (e.g. ap-singapore-1)")
    compartment_id: str = Field(..., min_length=10, description="Target Compartment OCID")
    monthly_budget: float = Field(default=0.0, ge=0.0, description="Monthly spending limit in USD for alerts")
    is_active: bool = Field(default=True, description="Whether to include this account in monitoring")

    @field_validator("key_file", mode="before")
    @classmethod
    def parse_key_path(cls, v: Any) -> Path:
        """Parse key_file string into Path object."""
        if isinstance(v, Path):
            return v
        return Path(str(v))

    def resolve_key_path(self, base_dir: Optional[Path] = None) -> Path:
        """Resolve the private key file path relative to base_dir or project root."""
        if self.key_file.is_absolute():
            return self.key_file
        root = base_dir if base_dir is not None else Path.cwd()
        return (root / self.key_file).resolve()

    def validate_key_file_exists(self, base_dir: Optional[Path] = None) -> bool:
        """Check if the private key file exists on disk."""
        resolved = self.resolve_key_path(base_dir)
        return resolved.is_file()

    def to_oci_config_dict(self, base_dir: Optional[Path] = None) -> Dict[str, str]:
        """Convert account config into dictionary required by OCI SDK.

        Note: Never log or print the output if it might expose paths to sensitive keys.
        """
        resolved_key = self.resolve_key_path(base_dir)
        return {
            "user": self.user_ocid,
            "key_file": str(resolved_key),
            "fingerprint": self.fingerprint,
            "tenancy": self.tenancy_ocid,
            "region": self.region,
        }


class AccountsContainer(BaseModel):
    """Wrapper model representing accounts.yaml structure."""

    accounts: List[AccountConfig] = Field(default_factory=list)


def load_accounts_config(
    file_path: Optional[Path] = None,
    check_keys_exist: bool = False,
    base_dir: Optional[Path] = None,
) -> List[AccountConfig]:
    """Load and validate OCI accounts from a YAML configuration file.

    Args:
        file_path: Path to accounts.yaml. If None, defaults to 'config/accounts.yaml'.
        check_keys_exist: If True, raises KeyFileNotFoundError if any .pem file is missing.
        base_dir: Base directory for resolving relative key_file paths. Defaults to cwd.

    Returns:
        List of validated AccountConfig objects.

    Raises:
        AccountsFileNotFoundError: If the YAML file does not exist.
        InvalidAccountConfigError: If YAML is malformed or validation fails.
        KeyFileNotFoundError: If check_keys_exist is True and a key file is missing.
    """
    target_path = file_path if file_path is not None else Path("config/accounts.yaml")

    if not target_path.is_file():
        logger.warning("Accounts configuration file not found at: %s", target_path)
        raise AccountsFileNotFoundError(f"Configuration file not found: {target_path}")

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        logger.error("Failed to parse YAML file at %s: %s", target_path, e)
        raise InvalidAccountConfigError(f"Malformed YAML in {target_path}: {e}") from e
    except Exception as e:
        logger.error("Error reading configuration file at %s: %s", target_path, e)
        raise ConfigError(f"Error reading {target_path}: {e}") from e

    if not raw_data:
        logger.info("Configuration file %s is empty", target_path)
        return []

    try:
        container = AccountsContainer.model_validate(raw_data)
    except Exception as e:
        logger.error("Validation error for accounts in %s: %s", target_path, e)
        raise InvalidAccountConfigError(f"Validation error in {target_path}: {e}") from e

    # Check key files if requested
    if check_keys_exist:
        for acc in container.accounts:
            if acc.is_active and not acc.validate_key_file_exists(base_dir):
                resolved = acc.resolve_key_path(base_dir)
                logger.error("Key file not found for account %s at %s", acc.account_id, resolved)
                raise KeyFileNotFoundError(
                    f"Private key file not found for account '{acc.account_id}': {resolved}"
                )

    logger.info("Successfully loaded %d accounts from %s", len(container.accounts), target_path)
    return container.accounts
