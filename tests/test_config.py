"""Unit tests for configuration module (settings & account parser)."""

from pathlib import Path
import pytest
from pydantic import ValidationError

from config.parser import (
    AccountConfig,
    AccountType,
    AccountsFileNotFoundError,
    InvalidAccountConfigError,
    KeyFileNotFoundError,
    load_accounts_config,
)
from config.settings import Settings


class TestSettings:
    """Tests for Pydantic Settings management."""

    def test_default_settings(self) -> None:
        """Verify default settings values when no environment is provided."""
        settings = Settings(
            TELEGRAM_BOT_TOKEN="",
            TELEGRAM_ADMIN_USER_ID=0,
            DATABASE_URL="sqlite+aiosqlite:///data/oci_bot.db",
            ACCOUNTS_CONFIG_PATH="config/accounts.yaml",
            DEFAULT_METRICS_INTERVAL_MINUTES=10,
            DEFAULT_BILLING_INTERVAL_HOURS=6,
        )
        assert not settings.is_telegram_configured
        assert settings.default_metrics_interval_minutes == 10
        assert settings.default_billing_interval_hours == 6
        assert settings.accounts_config_path == Path("config/accounts.yaml")
        assert settings.resolved_database_path == Path("data/oci_bot.db")

    def test_configured_telegram_settings(self) -> None:
        """Verify is_telegram_configured returns True when valid credentials are supplied."""
        settings = Settings(
            TELEGRAM_BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            TELEGRAM_ADMIN_USER_ID=987654321,
        )
        assert settings.is_telegram_configured
        assert settings.telegram_admin_user_id == 987654321


class TestAccountConfig:
    """Tests for AccountConfig model and path resolution."""

    def test_valid_account_config(self) -> None:
        """Test valid AccountConfig parsing."""
        acc = AccountConfig(
            account_id="acc_test",
            name="Test Account",
            account_type=AccountType.PAYG,
            tenancy_ocid="ocid1.tenancy.oc1..testtenancy",
            user_ocid="ocid1.user.oc1..testuser",
            fingerprint="aa:bb:cc:dd:ee:ff:11:22:33:44:55:66:77:88:99:00",
            key_file=Path("credentials/keys/test.pem"),
            region="ap-singapore-1",
            compartment_id="ocid1.compartment.oc1..testcompartment",
            monthly_budget=50.0,
            is_active=True,
        )
        assert acc.account_id == "acc_test"
        assert acc.account_type == AccountType.PAYG
        assert acc.monthly_budget == 50.0

        oci_dict = acc.to_oci_config_dict(base_dir=Path("/workspace"))
        assert oci_dict["user"] == "ocid1.user.oc1..testuser"
        assert oci_dict["region"] == "ap-singapore-1"
        assert oci_dict["fingerprint"] == "aa:bb:cc:dd:ee:ff:11:22:33:44:55:66:77:88:99:00"
        assert str(acc.resolve_key_path(base_dir=Path("/workspace"))) == "/workspace/credentials/keys/test.pem"

    def test_invalid_account_config_missing_field(self) -> None:
        """Test that validation fails when required fields are missing."""
        with pytest.raises(ValidationError):
            AccountConfig(
                account_id="acc_missing",
                name="Missing Fields",
                # missing tenancy, user, fingerprint, key_file, region, compartment_id
            )  # type: ignore[call-arg]

    def test_key_file_exists_check(self, tmp_path: Path) -> None:
        """Test key file existence checking."""
        dummy_key = tmp_path / "credentials" / "keys" / "valid.pem"
        dummy_key.parent.mkdir(parents=True, exist_ok=True)
        dummy_key.write_text("FAKE PEM CONTENT")

        acc = AccountConfig(
            account_id="acc_dummy",
            name="Dummy Key Account",
            account_type=AccountType.FREE_TIER,
            tenancy_ocid="ocid1.tenancy.oc1..dummy",
            user_ocid="ocid1.user.oc1..dummy",
            fingerprint="11:22:33:44:55:66:77:88:99:00:11:22:33:44:55:66",
            key_file=Path("credentials/keys/valid.pem"),
            region="ap-tokyo-1",
            compartment_id="ocid1.tenancy.oc1..dummy",
            monthly_budget=0.0,
        )
        assert acc.validate_key_file_exists(base_dir=tmp_path) is True

        missing_acc = AccountConfig(
            account_id="acc_missing_key",
            name="Missing Key Account",
            account_type=AccountType.FREE_TIER,
            tenancy_ocid="ocid1.tenancy.oc1..dummy",
            user_ocid="ocid1.user.oc1..dummy",
            fingerprint="11:22:33:44:55:66:77:88:99:00:11:22:33:44:55:66",
            key_file=Path("credentials/keys/non_existent.pem"),
            region="ap-tokyo-1",
            compartment_id="ocid1.tenancy.oc1..dummy",
            monthly_budget=0.0,
        )
        assert missing_acc.validate_key_file_exists(base_dir=tmp_path) is False


class TestLoadAccountsConfig:
    """Tests for YAML loader function."""

    def test_load_accounts_example(self) -> None:
        """Verify that template accounts.yaml.example loads exactly 3 accounts."""
        example_path = Path("config/accounts.yaml.example")
        accounts = load_accounts_config(file_path=example_path, check_keys_exist=False)

        assert len(accounts) == 3
        assert accounts[0].account_id == "acc_01"
        assert accounts[0].account_type == AccountType.PAYG
        assert accounts[0].monthly_budget == 75.0
        assert accounts[1].account_id == "acc_02"
        assert accounts[1].account_type == AccountType.FREE_TIER
        assert accounts[2].account_id == "acc_03"
        assert accounts[2].account_type == AccountType.FREE_TIER

    def test_missing_file_raises_error(self, tmp_path: Path) -> None:
        """Verify that loading a non-existent file raises AccountsFileNotFoundError."""
        non_existent = tmp_path / "not_found.yaml"
        with pytest.raises(AccountsFileNotFoundError):
            load_accounts_config(file_path=non_existent)

    def test_empty_yaml_returns_empty_list(self, tmp_path: Path) -> None:
        """Verify that an empty YAML file returns an empty list."""
        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("")
        accounts = load_accounts_config(file_path=empty_file)
        assert accounts == []

    def test_malformed_yaml_raises_error(self, tmp_path: Path) -> None:
        """Verify that invalid YAML syntax raises InvalidAccountConfigError."""
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("accounts: [unclosed list")
        with pytest.raises(InvalidAccountConfigError):
            load_accounts_config(file_path=bad_file)

    def test_check_keys_exist_flag(self, tmp_path: Path) -> None:
        """Verify that check_keys_exist=True raises KeyFileNotFoundError when key is missing."""
        cfg_file = tmp_path / "accounts.yaml"
        cfg_file.write_text(
            """
accounts:
  - account_id: "acc_nokey"
    name: "No Key"
    account_type: "FREE_TIER"
    tenancy_ocid: "ocid1.tenancy.oc1..dummy"
    user_ocid: "ocid1.user.oc1..dummy"
    fingerprint: "11:22:33:44:55:66:77:88:99:00:11:22:33:44:55:66"
    key_file: "credentials/keys/missing.pem"
    region: "us-ashburn-1"
    compartment_id: "ocid1.tenancy.oc1..dummy"
    monthly_budget: 0.0
    is_active: true
"""
        )
        with pytest.raises(KeyFileNotFoundError):
            load_accounts_config(file_path=cfg_file, check_keys_exist=True, base_dir=tmp_path)
