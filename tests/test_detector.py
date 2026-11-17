"""Unit tests for silent incident detector (ADR-002)."""

import pytest

from src.scheduler.detector import (
    IncidentAlert,
    IncidentDetector,
    IncidentSeverity,
    IncidentType,
)


class TestIncidentDetectorTransitions:
    """Tests for compute instance state transition watchdog rules."""

    def test_first_time_seen_is_silent(self) -> None:
        """Verify that observing an instance for the first time produces no alert."""
        alert = IncidentDetector.check_state_transition(
            account_id="acc_01",
            account_name="Production",
            instance_id="ocid1.instance.oc1..vm1",
            instance_name="web-01",
            previous_state=None,
            current_state="RUNNING",
        )
        assert alert is None

    def test_running_to_stopped_triggers_critical_alert(self) -> None:
        """Verify unexpected VM outage (RUNNING -> STOPPED) generates a critical push alert."""
        alert = IncidentDetector.check_state_transition(
            account_id="acc_01",
            account_name="Production",
            instance_id="ocid1.instance.oc1..vm1",
            instance_name="web-01",
            previous_state="RUNNING",
            current_state="STOPPED",
        )
        assert alert is not None
        assert alert.incident_type == IncidentType.VM_DOWN
        assert alert.severity == IncidentSeverity.CRITICAL
        assert alert.instance_name == "web-01"
        assert "Mati Mendadak" in alert.title

    def test_stopped_to_running_triggers_recovery_alert(self) -> None:
        """Verify VM recovery (STOPPED -> RUNNING) generates an informational recovery alert."""
        alert = IncidentDetector.check_state_transition(
            account_id="acc_01",
            account_name="Production",
            instance_id="ocid1.instance.oc1..vm1",
            instance_name="web-01",
            previous_state="STOPPED",
            current_state="RUNNING",
        )
        assert alert is not None
        assert alert.incident_type == IncidentType.VM_RECOVERED
        assert alert.severity == IncidentSeverity.INFO
        assert "Kembali Berjalan" in alert.title

    def test_steady_state_remains_silent(self) -> None:
        """Verify steady state (RUNNING -> RUNNING, STOPPED -> STOPPED) remains silent."""
        assert (
            IncidentDetector.check_state_transition(
                account_id="acc_01",
                account_name="Production",
                instance_id="ocid1.instance.oc1..vm1",
                instance_name="web-01",
                previous_state="RUNNING",
                current_state="RUNNING",
            )
            is None
        )
        assert (
            IncidentDetector.check_state_transition(
                account_id="acc_01",
                account_name="Production",
                instance_id="ocid1.instance.oc1..vm1",
                instance_name="web-01",
                previous_state="STOPPED",
                current_state="STOPPED",
            )
            is None
        )


class TestIncidentDetectorCpuSpike:
    """Tests for CPU utilization spike detection across consecutive cycles."""

    def test_cpu_normal_remains_silent(self) -> None:
        """Verify normal CPU (< 85%) produces no alert."""
        consecutive, alert = IncidentDetector.check_cpu_utilization(
            account_id="acc_01",
            account_name="Production",
            instance_id="ocid1.instance.oc1..vm1",
            instance_name="web-01",
            cpu_percent=45.0,
            previous_consecutive_high=0,
        )
        assert consecutive == 0
        assert alert is None

    def test_cpu_single_cycle_spike_remains_silent(self) -> None:
        """Verify spike on cycle 1 only increments counter without firing alert."""
        consecutive, alert = IncidentDetector.check_cpu_utilization(
            account_id="acc_01",
            account_name="Production",
            instance_id="ocid1.instance.oc1..vm1",
            instance_name="web-01",
            cpu_percent=92.0,
            previous_consecutive_high=0,
        )
        assert consecutive == 1
        assert alert is None

    def test_cpu_two_consecutive_cycles_fires_warning(self) -> None:
        """Verify spike on cycle 2 triggers a warning push alert."""
        consecutive, alert = IncidentDetector.check_cpu_utilization(
            account_id="acc_01",
            account_name="Production",
            instance_id="ocid1.instance.oc1..vm1",
            instance_name="web-01",
            cpu_percent=89.5,
            previous_consecutive_high=1,
        )
        assert consecutive == 2
        assert alert is not None
        assert alert.incident_type == IncidentType.HIGH_CPU_SPIKE
        assert alert.severity == IncidentSeverity.WARNING
        assert alert.metric_value == 89.5
        assert "Beban CPU Tinggi Beruntun" in alert.title

    def test_cpu_recovery_after_spike(self) -> None:
        """Verify return to normal CPU after previous alert generates a recovery alert."""
        consecutive, alert = IncidentDetector.check_cpu_utilization(
            account_id="acc_01",
            account_name="Production",
            instance_id="ocid1.instance.oc1..vm1",
            instance_name="web-01",
            cpu_percent=30.0,
            previous_consecutive_high=2,
        )
        assert consecutive == 0
        assert alert is not None
        assert alert.incident_type == IncidentType.HIGH_CPU_RESOLVED
        assert alert.severity == IncidentSeverity.INFO
        assert "Kembali Normal" in alert.title


class TestIncidentDetectorBudget:
    """Tests for linear forecast budget limit detection."""

    def test_free_tier_no_budget_alert(self) -> None:
        """Verify Free Tier (budget=0.0) produces no alert."""
        alert = IncidentDetector.check_budget_limit(
            account_id="acc_02",
            account_name="Free Tier",
            forecast_spend=0.0,
            monthly_budget=0.0,
        )
        assert alert is None

    def test_within_budget_remains_silent(self) -> None:
        """Verify forecast within budget produces no alert."""
        alert = IncidentDetector.check_budget_limit(
            account_id="acc_01",
            account_name="Production",
            forecast_spend=45.0,
            monthly_budget=50.0,
        )
        assert alert is None

    def test_budget_exceeded_triggers_alert(self) -> None:
        """Verify forecast exceeding budget triggers a warning push alert."""
        alert = IncidentDetector.check_budget_limit(
            account_id="acc_01",
            account_name="Production",
            forecast_spend=85.0,
            monthly_budget=50.0,
            currency="USD",
        )
        assert alert is not None
        assert alert.incident_type == IncidentType.BUDGET_EXCEEDED
        assert alert.severity == IncidentSeverity.WARNING
        assert alert.metric_value == 85.0
        assert "Melebihi Budget" in alert.title
