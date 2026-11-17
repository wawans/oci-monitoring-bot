"""Incident detector for silent watchdog monitoring (ADR-002)."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class IncidentType(str, Enum):
    """Categorized types of incidents monitored by the silent watchdog."""

    VM_DOWN = "VM_DOWN"
    VM_RECOVERED = "VM_RECOVERED"
    HIGH_CPU_SPIKE = "HIGH_CPU_SPIKE"
    HIGH_CPU_RESOLVED = "HIGH_CPU_RESOLVED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


class IncidentSeverity(str, Enum):
    """Severity classification for alerts."""

    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class IncidentAlert:
    """Incident event payload dispatched to alert notification channels."""

    incident_type: IncidentType
    severity: IncidentSeverity
    account_id: str
    account_name: str
    title: str
    message: str
    timestamp: datetime
    instance_id: Optional[str] = None
    instance_name: Optional[str] = None
    metric_value: Optional[float] = None


class IncidentDetector:
    """Evaluates metrics and compute states to detect anomalies and recoveries.

    Silent Watchdog Principle:
    Bot berjalan senyap di latar belakang dan HANYA menghasilkan IncidentAlert
    jika terdeteksi anomali atau pemulihan status.
    """

    CPU_THRESHOLD_PERCENT: float = 85.0
    CPU_CONSECUTIVE_CYCLES_ALERT: int = 2

    @classmethod
    def check_state_transition(
        cls,
        account_id: str,
        account_name: str,
        instance_id: str,
        instance_name: str,
        previous_state: Optional[str],
        current_state: str,
    ) -> Optional[IncidentAlert]:
        """Detect unexpected lifecycle transitions (down or recovery).

        Args:
            account_id: Account identifier.
            account_name: Account friendly display name.
            instance_id: OCID of the instance.
            instance_name: Display name of the instance.
            previous_state: Previous recorded lifecycle state (e.g. RUNNING, STOPPED).
            current_state: Newly observed lifecycle state.

        Returns:
            IncidentAlert if transition represents an unexpected failure or recovery, else None.
        """
        now = datetime.now(timezone.utc)
        curr = current_state.upper()
        prev = previous_state.upper() if previous_state else None

        # First time seeing the instance: do not fire alert
        if prev is None:
            return None

        # Anomaly: Instance was RUNNING but is now STOPPED or CRITICAL
        if prev == "RUNNING" and curr in {"STOPPED", "CRITICAL"}:
            logger.warning(
                "Incident detected: VM %s (%s) transitioned from %s to %s",
                instance_name,
                instance_id,
                prev,
                curr,
            )
            return IncidentAlert(
                incident_type=IncidentType.VM_DOWN,
                severity=IncidentSeverity.CRITICAL,
                account_id=account_id,
                account_name=account_name,
                instance_id=instance_id,
                instance_name=instance_name,
                title="🚨 Alert: Instance Mati Mendadak",
                message=(
                    f"Instance <b>{instance_name}</b> pada akun <b>{account_name}</b> "
                    f"berubah status dari <code>{prev}</code> menjadi <code>{curr}</code>!"
                ),
                timestamp=now,
            )

        # Recovery: Instance was STOPPED or CRITICAL but is now RUNNING
        if prev in {"STOPPED", "CRITICAL"} and curr == "RUNNING":
            logger.info(
                "Recovery detected: VM %s (%s) transitioned from %s to %s",
                instance_name,
                instance_id,
                prev,
                curr,
            )
            return IncidentAlert(
                incident_type=IncidentType.VM_RECOVERED,
                severity=IncidentSeverity.INFO,
                account_id=account_id,
                account_name=account_name,
                instance_id=instance_id,
                instance_name=instance_name,
                title="✅ Pemulihan: Instance Kembali Berjalan",
                message=(
                    f"Instance <b>{instance_name}</b> pada akun <b>{account_name}</b> "
                    f"telah pulih dan kembali berstatus <code>RUNNING</code>."
                ),
                timestamp=now,
            )

        return None

    @classmethod
    def check_cpu_utilization(
        cls,
        account_id: str,
        account_name: str,
        instance_id: str,
        instance_name: str,
        cpu_percent: Optional[float],
        previous_consecutive_high: int,
    ) -> Tuple[int, Optional[IncidentAlert]]:
        """Evaluate CPU threshold over consecutive polling cycles.

        Rule:
        Kirim Push Alert jika CPU > 85% selama 2 siklus berurutan.

        Args:
            account_id: Account identifier.
            account_name: Account display name.
            instance_id: OCID of the instance.
            instance_name: Display name of the instance.
            cpu_percent: Current measured CPU percentage (or None if offline).
            previous_consecutive_high: Count of prior consecutive high-cpu cycles.

        Returns:
            Tuple of (new_consecutive_count, Optional[IncidentAlert]).
        """
        now = datetime.now(timezone.utc)

        if cpu_percent is None:
            # Cannot determine CPU; keep existing count
            return previous_consecutive_high, None

        if cpu_percent > cls.CPU_THRESHOLD_PERCENT:
            new_consecutive = previous_consecutive_high + 1
            logger.debug(
                "Instance %s CPU %.1f%% exceeds threshold (cycle %d)",
                instance_name,
                cpu_percent,
                new_consecutive,
            )

            # Fire alert exactly when reaching the threshold consecutive count
            if new_consecutive == cls.CPU_CONSECUTIVE_CYCLES_ALERT:
                alert = IncidentAlert(
                    incident_type=IncidentType.HIGH_CPU_SPIKE,
                    severity=IncidentSeverity.WARNING,
                    account_id=account_id,
                    account_name=account_name,
                    instance_id=instance_id,
                    instance_name=instance_name,
                    metric_value=cpu_percent,
                    title="⚠️ Warning: Beban CPU Tinggi Beruntun",
                    message=(
                        f"Instance <b>{instance_name}</b> pada akun <b>{account_name}</b> "
                        f"mengalami utilisasi CPU <b>{cpu_percent:.1f}%</b> (> {cls.CPU_THRESHOLD_PERCENT:.0f}%) "
                        f"selama {cls.CPU_CONSECUTIVE_CYCLES_ALERT} siklus pemantauan berurutan!"
                    ),
                    timestamp=now,
                )
                return new_consecutive, alert

            return new_consecutive, None

        # CPU is normal
        if previous_consecutive_high >= cls.CPU_CONSECUTIVE_CYCLES_ALERT:
            # Resolved previous high CPU
            alert = IncidentAlert(
                incident_type=IncidentType.HIGH_CPU_RESOLVED,
                severity=IncidentSeverity.INFO,
                account_id=account_id,
                account_name=account_name,
                instance_id=instance_id,
                instance_name=instance_name,
                metric_value=cpu_percent,
                title="🟢 Info: Beban CPU Kembali Normal",
                message=(
                    f"Utilisasi CPU pada instance <b>{instance_name}</b> ({account_name}) "
                    f"telah normal kembali di level <b>{cpu_percent:.1f}%</b>."
                ),
                timestamp=now,
            )
            return 0, alert

        return 0, None

    @classmethod
    def check_budget_limit(
        cls,
        account_id: str,
        account_name: str,
        forecast_spend: float,
        monthly_budget: float,
        currency: str = "USD",
    ) -> Optional[IncidentAlert]:
        """Check whether projected linear run-rate spend breaches monthly budget.

        Args:
            account_id: Account identifier.
            account_name: Account display name.
            forecast_spend: Projected spend by end of calendar month.
            monthly_budget: Target spending budget.
            currency: Currency code (defaults to USD).

        Returns:
            IncidentAlert if forecast exceeds non-zero monthly budget, else None.
        """
        now = datetime.now(timezone.utc)

        if monthly_budget > 0.0 and forecast_spend > monthly_budget:
            logger.warning(
                "Budget breach on account %s: Forecast %s %.2f > Budget %s %.2f",
                account_id,
                currency,
                forecast_spend,
                currency,
                monthly_budget,
            )
            return IncidentAlert(
                incident_type=IncidentType.BUDGET_EXCEEDED,
                severity=IncidentSeverity.WARNING,
                account_id=account_id,
                account_name=account_name,
                metric_value=forecast_spend,
                title="💸 Alert: Proyeksi Biaya Melebihi Budget",
                message=(
                    f"Proyeksi pengeluaran bulan ini untuk akun <b>{account_name}</b> "
                    f"diperkirakan mencapai <b>{currency} {forecast_spend:.2f}</b>, "
                    f"melampaui target budget <b>{currency} {monthly_budget:.2f}</b>!"
                ),
                timestamp=now,
            )

        return None
