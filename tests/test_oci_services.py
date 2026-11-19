"""Unit tests for OCI Multi-Account Service Layer with mocked OCI SDK interactions."""

import calendar
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from oci.exceptions import ServiceError

from config.parser import AccountConfig, AccountType
from src.oci_services.billing import BillingService, BillingSummary
from src.oci_services.client_factory import (
    ClientInitializationError,
    OCIClientBundle,
    OCIClientFactory,
)
from src.oci_services.compute import (
    ComputeActionError,
    ComputeService,
    ComputeServiceError,
    InstanceInfo,
)
from src.oci_services.monitoring import MonitoringService


@pytest.fixture
def dummy_key(tmp_path: Path) -> Path:
    """Fixture providing a mock RSA private key file for OCI authentication."""
    key_dir = tmp_path / "credentials" / "keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    key_file = key_dir / "test_rsa.pem"
    key_file.write_text(
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA0mockkeymockkeymockkeymockkeymockkeymockkeymockkey\n"
        "-----END RSA PRIVATE KEY-----\n"
    )
    return key_file


@pytest.fixture
def mock_account(dummy_key: Path) -> AccountConfig:
    """Fixture providing a valid AccountConfig for testing."""
    return AccountConfig(
        account_id="acc_unit_test",
        name="Unit Test Account",
        account_type=AccountType.PAYG,
        tenancy_ocid="ocid1.tenancy.oc1..unittestenancy",
        user_ocid="ocid1.user.oc1..unittestuser",
        fingerprint="20:3b:97:13:55:1c:11:0d:43:dc:14:28:b5:12:34:56",
        key_file=dummy_key,
        region="ap-singapore-1",
        compartment_id="ocid1.compartment.oc1..unittestcomp",
        monthly_budget=50.0,
        is_active=True,
    )


@pytest.fixture
def mock_bundle(mock_account: AccountConfig) -> OCIClientBundle:
    """Fixture providing a mock OCIClientBundle with mocked OCI clients."""
    compute_client = MagicMock()
    network_client = MagicMock()
    monitoring_client = MagicMock()
    usage_client = MagicMock()

    return OCIClientBundle(
        account_id=mock_account.account_id,
        account_name=mock_account.name,
        account_type=mock_account.account_type,
        compartment_id=mock_account.compartment_id,
        region=mock_account.region,
        monthly_budget=mock_account.monthly_budget,
        compute_client=compute_client,
        network_client=network_client,
        monitoring_client=monitoring_client,
        usage_client=usage_client,
        raw_config={"tenancy": mock_account.tenancy_ocid, "region": mock_account.region},
    )


class TestOCIClientFactory:
    """Tests for OCI client factory, per-account fault isolation, and handshake verification."""

    @patch("src.oci_services.client_factory.oci.config.validate_config")
    @patch("src.oci_services.client_factory.ComputeClient")
    @patch("src.oci_services.client_factory.VirtualNetworkClient")
    @patch("src.oci_services.client_factory.MonitoringClient")
    @patch("src.oci_services.client_factory.UsageapiClient")
    def test_create_bundle_success(
        self,
        mock_usage: MagicMock,
        mock_mon: MagicMock,
        mock_net: MagicMock,
        mock_comp: MagicMock,
        mock_val: MagicMock,
        mock_account: AccountConfig,
    ) -> None:
        """Verify successful client bundle instantiation."""
        factory = OCIClientFactory()
        bundle = factory.create_bundle(mock_account)

        assert bundle.account_id == "acc_unit_test"
        assert bundle.account_type == AccountType.PAYG
        assert bundle.compartment_id == mock_account.compartment_id
        mock_val.assert_called_once()

    def test_create_bundle_missing_key_raises_error(self, tmp_path: Path) -> None:
        """Verify ClientInitializationError when key file does not exist."""
        bad_account = AccountConfig(
            account_id="acc_missing_key",
            name="Missing Key",
            account_type=AccountType.FREE_TIER,
            tenancy_ocid="ocid1.tenancy.oc1..test",
            user_ocid="ocid1.user.oc1..test",
            fingerprint="aa:bb:cc:dd:ee:ff:11:22:33:44:55:66:77:88:99:00",
            key_file=Path("credentials/keys/non_existent.pem"),
            region="us-ashburn-1",
            compartment_id="ocid1.compartment.oc1..test",
        )
        factory = OCIClientFactory(base_dir=tmp_path)
        with pytest.raises(ClientInitializationError):
            factory.create_bundle(bad_account)

    @patch("src.oci_services.client_factory.OCIClientFactory.create_bundle")
    def test_initialize_clients_fault_isolation(
        self,
        mock_create: MagicMock,
        mock_account: AccountConfig,
    ) -> None:
        """Verify that a failure in Account A does not crash initialization of Account B."""
        account_bad = AccountConfig(
            account_id="acc_bad",
            name="Bad Account",
            account_type=AccountType.FREE_TIER,
            tenancy_ocid="ocid1.tenancy.oc1..bad",
            user_ocid="ocid1.user.oc1..bad",
            fingerprint="11:22:33:44:55:66:77:88:99:00:11:22:33:44:55:66",
            key_file=Path("credentials/keys/bad.pem"),
            region="us-ashburn-1",
            compartment_id="ocid1.compartment.oc1..bad",
            is_active=True,
        )

        mock_bundle_good = MagicMock()
        mock_bundle_good.account_id = mock_account.account_id

        def side_effect(acc: AccountConfig) -> MagicMock:
            if acc.account_id == "acc_bad":
                raise ClientInitializationError("Simulated bad account failure")
            return mock_bundle_good

        mock_create.side_effect = side_effect

        factory = OCIClientFactory()
        bundles = factory.initialize_clients([account_bad, mock_account])

        # Account bad failed, but mock_account succeeded
        assert "acc_bad" not in bundles
        assert mock_account.account_id in bundles
        assert len(bundles) == 1

    async def test_verify_handshake(self, mock_bundle: OCIClientBundle) -> None:
        """Verify asynchronous handshake verification behavior."""
        factory = OCIClientFactory()
        factory._bundles[mock_bundle.account_id] = mock_bundle

        # Case 1: Handshake success
        mock_bundle.compute_client.list_instances.return_value = MagicMock(data=[])
        assert await factory.verify_handshake(mock_bundle.account_id) is True

        # Case 2: Handshake failure via exception
        mock_bundle.compute_client.list_instances.side_effect = Exception("Auth failed")
        assert await factory.verify_handshake(mock_bundle.account_id) is False

        # Case 3: Unknown account
        assert await factory.verify_handshake("non_existent_account") is False


class TestComputeService:
    """Tests for compute instance listing, IP resolution, and power actions."""

    async def test_resolve_instance_ips(self, mock_bundle: OCIClientBundle) -> None:
        """Test VNIC query and IP address resolution."""
        service = ComputeService()

        # Mock list_vnic_attachments
        mock_attachment = MagicMock()
        mock_attachment.lifecycle_state = "ATTACHED"
        mock_attachment.vnic_id = "ocid1.vnic.oc1..vnic123"
        mock_bundle.compute_client.list_vnic_attachments.return_value = MagicMock(
            data=[mock_attachment]
        )

        # Mock get_vnic
        mock_vnic = MagicMock()
        mock_vnic.public_ip = "129.150.10.5"
        mock_vnic.private_ip = "10.0.0.12"
        mock_bundle.network_client.get_vnic.return_value = MagicMock(data=mock_vnic)

        pub_ip, priv_ip = await service.resolve_instance_ips(
            mock_bundle, "ocid1.instance.oc1..vm1"
        )
        assert pub_ip == "129.150.10.5"
        assert priv_ip == "10.0.0.12"

    async def test_list_instances(self, mock_bundle: OCIClientBundle) -> None:
        """Test listing instances with resolved network details."""
        service = ComputeService()

        vm1 = MagicMock()
        vm1.id = "ocid1.instance.oc1..vm1"
        vm1.display_name = "prod-api-server"
        vm1.shape = "VM.Standard.A1.Flex"
        vm1.lifecycle_state = "RUNNING"

        vm2 = MagicMock()
        vm2.id = "ocid1.instance.oc1..vm2"
        vm2.display_name = "old-dead-server"
        vm2.shape = "VM.Standard2.1"
        vm2.lifecycle_state = "TERMINATED"

        mock_bundle.compute_client.list_instances.return_value = MagicMock(
            data=[vm1, vm2]
        )

        # Patch resolve_instance_ips to avoid nested VNIC calls
        with patch.object(
            service, "resolve_instance_ips", return_value=("140.238.1.1", "10.0.0.2")
        ):
            instances = await service.list_instances(mock_bundle, include_terminated=False)

        assert len(instances) == 1
        inst = instances[0]
        assert inst.instance_id == "ocid1.instance.oc1..vm1"
        assert inst.display_name == "prod-api-server"
        assert inst.lifecycle_state == "RUNNING"
        assert inst.public_ip == "140.238.1.1"
        assert inst.private_ip == "10.0.0.2"

    async def test_execute_action_success(self, mock_bundle: OCIClientBundle) -> None:
        """Test executing valid power actions (START, STOP, SOFTRESET)."""
        service = ComputeService()

        mock_bundle.compute_client.instance_action.return_value = MagicMock()

        assert await service.execute_action(
            mock_bundle, "ocid1.instance.oc1..vm1", "START"
        ) is True
        assert await service.execute_action(
            mock_bundle, "ocid1.instance.oc1..vm1", "stop"
        ) is True
        assert await service.execute_action(
            mock_bundle, "ocid1.instance.oc1..vm1", "SOFTRESET"
        ) is True

    async def test_execute_action_invalid_or_rejected(self, mock_bundle: OCIClientBundle) -> None:
        """Test executing invalid action or API rejection."""
        service = ComputeService()

        # Invalid action name
        with pytest.raises(ComputeActionError) as exc_info:
            await service.execute_action(mock_bundle, "ocid1.instance.oc1..vm1", "TERMINATE")
        assert "Invalid compute action" in str(exc_info.value)

        # API rejection
        mock_bundle.compute_client.instance_action.side_effect = Exception("Instance in conflict")
        with pytest.raises(ComputeActionError) as exc_info:
            await service.execute_action(mock_bundle, "ocid1.instance.oc1..vm1", "STOP")
        assert "OCI API rejected" in str(exc_info.value)


class TestMonitoringService:
    """Tests for CPU utilization metric polling and history extraction."""

    async def test_get_latest_cpu_utilization(self, mock_bundle: OCIClientBundle) -> None:
        """Test parsing latest CPU metric datapoint from MQL query."""
        service = MonitoringService()

        dp1 = MagicMock()
        dp1.timestamp = datetime(2026, 11, 17, 6, 0, 0, tzinfo=timezone.utc)
        dp1.value = 14.2

        dp2 = MagicMock()
        dp2.timestamp = datetime(2026, 11, 17, 6, 5, 0, tzinfo=timezone.utc)
        dp2.value = 88.5

        metric_data = MagicMock()
        metric_data.aggregated_datapoints = [dp1, dp2]

        mock_bundle.monitoring_client.summarize_metrics_data.return_value = MagicMock(
            data=[metric_data]
        )

        cpu = await service.get_latest_cpu_utilization(
            mock_bundle, "ocid1.instance.oc1..vm1"
        )
        assert cpu == 88.5

        # Verify that SummarizeMetricsDataDetails includes required namespace
        call_args = mock_bundle.monitoring_client.summarize_metrics_data.call_args
        details = call_args[1]["summarize_metrics_data_details"]
        assert details.namespace == "oci_computeagent"
        assert 'resourceId = "ocid1.instance.oc1..vm1"' in details.query
        assert details.resolution == "1m"

    async def test_get_cpu_history(self, mock_bundle: OCIClientBundle) -> None:
        """Test retrieving CPU historical time-series points and namespace requirement."""
        service = MonitoringService()

        dp1 = MagicMock()
        dp1.timestamp = datetime(2026, 11, 17, 0, 0, 0, tzinfo=timezone.utc)
        dp1.value = 25.0

        dp2 = MagicMock()
        dp2.timestamp = datetime(2026, 11, 17, 1, 0, 0, tzinfo=timezone.utc)
        dp2.value = 35.5

        metric_data = MagicMock()
        metric_data.aggregated_datapoints = [dp2, dp1]

        mock_bundle.monitoring_client.summarize_metrics_data.return_value = MagicMock(
            data=[metric_data]
        )

        history = await service.get_cpu_history(mock_bundle, "ocid1.instance.oc1..vm1", hours=6)
        assert len(history) == 2
        # Verify sorted ascending by timestamp
        assert history[0][1] == 25.0
        assert history[1][1] == 35.5

        # Verify namespace is oci_computeagent
        call_args = mock_bundle.monitoring_client.summarize_metrics_data.call_args
        details = call_args[1]["summarize_metrics_data_details"]
        assert details.namespace == "oci_computeagent"
        assert details.resolution == "5m"

    async def test_get_latest_cpu_empty_or_error(self, mock_bundle: OCIClientBundle) -> None:
        """Test that missing datapoints or query error returns None gracefully."""
        service = MonitoringService()

        # Case 1: Empty datapoints
        metric_data = MagicMock()
        metric_data.aggregated_datapoints = []
        mock_bundle.monitoring_client.summarize_metrics_data.return_value = MagicMock(
            data=[metric_data]
        )
        assert await service.get_latest_cpu_utilization(
            mock_bundle, "ocid1.instance.oc1..vm1"
        ) is None

        # Case 2: Exception raised
        mock_bundle.monitoring_client.summarize_metrics_data.side_effect = Exception("Metrics API offline")
        assert await service.get_latest_cpu_utilization(
            mock_bundle, "ocid1.instance.oc1..vm1"
        ) is None


class TestBillingService:
    """Tests for billing usage retrieval, linear run-rate forecast, and Free Tier fallback."""

    def test_calculate_linear_forecast(self) -> None:
        """Verify linear forecast formula calculation (ADR-003)."""
        service = BillingService()

        # Reference time: 10th of November 2026 (November has 30 days)
        ref_time = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)
        mtd_spend = 20.0  # $20 over 10 days = $2.00/day * 30 days = $60.00
        forecast = service.calculate_linear_forecast(mtd_spend, current_time=ref_time)
        assert forecast == 60.0

    async def test_free_tier_fallback(self, mock_bundle: OCIClientBundle) -> None:
        """Verify FREE_TIER account gracefully returns $0.00 without querying Usage API."""
        mock_bundle.account_type = AccountType.FREE_TIER
        service = BillingService()

        summary = await service.get_billing_summary(mock_bundle)
        assert summary.mtd_spend == 0.0
        assert summary.forecast_spend == 0.0
        assert summary.is_budget_exceeded is False
        mock_bundle.usage_client.request_summarized_usages.assert_not_called()

    async def test_payg_billing_and_budget_exceeded(self, mock_bundle: OCIClientBundle) -> None:
        """Verify PAYG account spend calculation and budget alert detection."""
        mock_bundle.account_type = AccountType.PAYG
        mock_bundle.monthly_budget = 40.0

        item1 = MagicMock()
        item1.computed_amount = 15.50
        item1.currency = "USD"

        item2 = MagicMock()
        item2.computed_amount = 10.00
        item2.currency = "USD"

        mock_bundle.usage_client.request_summarized_usages.return_value = MagicMock(
            data=MagicMock(items=[item1, item2])
        )

        service = BillingService()
        # Ref time: Nov 10 (day 10). Total spend = $25.50. Run-rate = 2.55/day * 30 = 76.50
        ref_time = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)
        summary = await service.get_billing_summary(mock_bundle, current_time=ref_time)

        assert summary.mtd_spend == 25.50
        assert summary.forecast_spend == 76.50
        assert summary.is_budget_exceeded is True

        # Verify UTC zero-hour precision on request details
        call_args = mock_bundle.usage_client.request_summarized_usages.call_args
        details = call_args[1]["request_summarized_usages_details"]
        assert details.time_usage_started == datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert details.time_usage_ended == datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert details.time_usage_started.hour == 0
        assert details.time_usage_started.minute == 0
        assert details.time_usage_started.second == 0
        assert details.time_usage_started.microsecond == 0
        assert details.time_usage_ended.hour == 0
        assert details.time_usage_ended.minute == 0
        assert details.time_usage_ended.second == 0
        assert details.time_usage_ended.microsecond == 0

    async def test_payg_billing_december_year_rollover(self, mock_bundle: OCIClientBundle) -> None:
        """Verify Usage API date precision and year rollover when querying December."""
        mock_bundle.account_type = AccountType.PAYG
        mock_bundle.usage_client.request_summarized_usages.return_value = MagicMock(
            data=MagicMock(items=[])
        )

        service = BillingService()
        ref_time = datetime(2026, 12, 15, 14, 25, 30, 123456, tzinfo=timezone.utc)
        await service.get_billing_summary(mock_bundle, current_time=ref_time)

        call_args = mock_bundle.usage_client.request_summarized_usages.call_args
        details = call_args[1]["request_summarized_usages_details"]
        assert details.time_usage_started == datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert details.time_usage_ended == datetime(2027, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert details.time_usage_ended.year == 2027
        assert details.time_usage_ended.month == 1
        assert details.time_usage_ended.day == 1
        assert details.time_usage_ended.hour == 0
        assert details.time_usage_ended.microsecond == 0

    async def test_payg_usage_api_service_error_graceful_fallback(
        self, mock_bundle: OCIClientBundle
    ) -> None:
        """Verify graceful fallback to $0.00 when Usage API raises ServiceError (Rule 2.2)."""
        mock_bundle.account_type = AccountType.PAYG

        error = ServiceError(
            status=404,
            code="NotAuthorizedOrNotFound",
            headers={},
            message="Tenancy not authorized or billing not enabled",
        )
        mock_bundle.usage_client.request_summarized_usages.side_effect = error

        service = BillingService()
        summary = await service.get_billing_summary(mock_bundle)

        assert summary.mtd_spend == 0.0
        assert summary.forecast_spend == 0.0
        assert summary.is_budget_exceeded is False
