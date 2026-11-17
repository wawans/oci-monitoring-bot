"""OCI Telemetry and Monitoring Service."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import oci
from oci.monitoring.models import SummarizeMetricsDataDetails

from src.oci_services.client_factory import OCIClientBundle

logger = logging.getLogger(__name__)


class MonitoringService:
    """Service handling metrics polling and CPU telemetry retrieval via OCI Monitoring API."""

    @staticmethod
    def _sync_get_cpu_metric(
        bundle: OCIClientBundle,
        instance_id: str,
        window_minutes: int = 15,
    ) -> Optional[float]:
        """Synchronously query latest CPU utilization percentage from oci_computeagent."""
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(minutes=window_minutes)

        query = f'CpuUtilization[1m]{{resourceId = "{instance_id}"}}.mean()'
        details = SummarizeMetricsDataDetails(
            query=query,
            start_time=start_time,
            end_time=now,
            resolution="1m",
        )

        try:
            response = bundle.monitoring_client.summarize_metrics_data(
                compartment_id=bundle.compartment_id,
                summarize_metrics_data_details=details,
            )
            metric_data_list = response.data or []

            for metric_data in metric_data_list:
                datapoints = getattr(metric_data, "aggregated_datapoints", None) or []
                if datapoints:
                    # Sort by timestamp ascending and get the most recent reading
                    sorted_points = sorted(datapoints, key=lambda p: p.timestamp)
                    latest_value = sorted_points[-1].value
                    if latest_value is not None:
                        return round(float(latest_value), 2)

            return None
        except Exception as e:
            logger.warning(
                "Unable to retrieve CPU metric for instance %s on account %s: %s",
                instance_id,
                bundle.account_id,
                e,
            )
            return None

    async def get_latest_cpu_utilization(
        self,
        bundle: OCIClientBundle,
        instance_id: str,
        window_minutes: int = 15,
    ) -> Optional[float]:
        """Asynchronously retrieve the most recent CPU utilization percentage.

        Args:
            bundle: Target account OCI client bundle.
            instance_id: OCID of the target compute instance.
            window_minutes: Query lookback window in minutes (default 15).

        Returns:
            Latest CPU percentage (0.0 to 100.0) or None if unavailable/offline.
        """
        return await asyncio.to_thread(
            self._sync_get_cpu_metric, bundle, instance_id, window_minutes
        )

    @staticmethod
    def _sync_get_cpu_history(
        bundle: OCIClientBundle,
        instance_id: str,
        hours: int = 24,
    ) -> List[Tuple[datetime, float]]:
        """Synchronously fetch historical CPU datapoints for chart rendering."""
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=hours)

        query = f'CpuUtilization[5m]{{resourceId = "{instance_id}"}}.mean()'
        details = SummarizeMetricsDataDetails(
            query=query,
            start_time=start_time,
            end_time=now,
            resolution="5m",
        )

        try:
            response = bundle.monitoring_client.summarize_metrics_data(
                compartment_id=bundle.compartment_id,
                summarize_metrics_data_details=details,
            )
            history: List[Tuple[datetime, float]] = []
            metric_data_list = response.data or []

            for metric_data in metric_data_list:
                datapoints = getattr(metric_data, "aggregated_datapoints", None) or []
                for p in datapoints:
                    if p.timestamp and p.value is not None:
                        history.append((p.timestamp, round(float(p.value), 2)))

            history.sort(key=lambda item: item[0])
            return history
        except Exception as e:
            logger.warning(
                "Failed fetching CPU history for instance %s on account %s: %s",
                instance_id,
                bundle.account_id,
                e,
            )
            return []

    async def get_cpu_history(
        self,
        bundle: OCIClientBundle,
        instance_id: str,
        hours: int = 24,
    ) -> List[Tuple[datetime, float]]:
        """Asynchronously fetch historical CPU datapoints for plotting."""
        return await asyncio.to_thread(self._sync_get_cpu_history, bundle, instance_id, hours)
