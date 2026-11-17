"""OCI Billing, Cost Tracking, and Linear Run-Rate Forecast Service."""

import asyncio
import calendar
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import oci
from oci.exceptions import ServiceError
from oci.usage_api.models import RequestSummarizedUsagesDetails

from config.parser import AccountType
from src.oci_services.client_factory import OCIClientBundle

logger = logging.getLogger(__name__)


@dataclass
class BillingSummary:
    """Consolidated billing summary and run-rate forecast for an account."""

    account_id: str
    account_name: str
    account_type: AccountType
    mtd_spend: float
    forecast_spend: float
    monthly_budget: float
    currency: str
    billing_period: str
    is_budget_exceeded: bool
    recorded_at: datetime


class BillingService:
    """Service handling Usage API queries, linear forecast calculation, and Free Tier fallback."""

    @staticmethod
    def calculate_linear_forecast(
        mtd_spend: float,
        current_time: Optional[datetime] = None,
    ) -> float:
        """Calculate month-end projected spend using linear run-rate algorithm (ADR-003).

        Formula:
            Forecast = (Biaya Aktual MTD / Hari Berjalan) * Total Hari Bulan Ini
        """
        now = current_time if current_time is not None else datetime.now(timezone.utc)
        total_days = calendar.monthrange(now.year, now.month)[1]
        days_elapsed = max(now.day, 1)

        daily_run_rate = mtd_spend / days_elapsed
        projected = daily_run_rate * total_days
        return round(projected, 2)

    def _sync_get_billing_summary(
        self,
        bundle: OCIClientBundle,
        current_time: Optional[datetime] = None,
    ) -> BillingSummary:
        """Synchronously query Usage API and compute forecast with graceful fallback."""
        now = current_time if current_time is not None else datetime.now(timezone.utc)
        billing_period = now.strftime("%Y-%m")
        currency = "USD"

        # Graceful handling for Free Tier accounts (ADR-003 & Rule 2.2)
        if bundle.account_type == AccountType.FREE_TIER:
            logger.debug(
                "Account %s is FREE_TIER. Returning $0.00 without querying Usage API.",
                bundle.account_id,
            )
            return BillingSummary(
                account_id=bundle.account_id,
                account_name=bundle.account_name,
                account_type=bundle.account_type,
                mtd_spend=0.0,
                forecast_spend=0.0,
                monthly_budget=bundle.monthly_budget,
                currency=currency,
                billing_period=billing_period,
                is_budget_exceeded=False,
                recorded_at=now,
            )

        start_of_month = datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=timezone.utc)
        tenancy_id = bundle.raw_config.get("tenancy", "")

        details = RequestSummarizedUsagesDetails(
            tenant_id=tenancy_id,
            time_usage_started=start_of_month,
            time_usage_ended=now,
            granularity="MONTHLY",
            query_type="COST",
        )

        mtd_spend = 0.0

        try:
            response = bundle.usage_client.request_summarized_usages(
                request_summarized_usages_details=details
            )
            items = getattr(response.data, "items", None) or []

            for item in items:
                amount = getattr(item, "computed_amount", None)
                if amount is not None:
                    mtd_spend += float(amount)
                item_currency = getattr(item, "currency", None)
                if item_currency:
                    currency = item_currency

            mtd_spend = round(mtd_spend, 2)

        except ServiceError as e:
            # Graceful Fallback Free Tier / Inaccessible Usage API:
            # Akun bertipe FREE_TIER atau akun tanpa histori tagihan tidak boleh crash.
            logger.warning(
                "Usage API ServiceError on account %s (%s): %s. Falling back to $0.00.",
                bundle.account_id,
                e.status,
                e.message,
            )
            mtd_spend = 0.0

        except Exception as e:
            logger.error(
                "Unexpected error querying Usage API for account %s: %s. Falling back to $0.00.",
                bundle.account_id,
                e,
            )
            mtd_spend = 0.0

        forecast_spend = self.calculate_linear_forecast(mtd_spend, now)
        is_exceeded = (
            bundle.monthly_budget > 0.0 and forecast_spend > bundle.monthly_budget
        )

        return BillingSummary(
            account_id=bundle.account_id,
            account_name=bundle.account_name,
            account_type=bundle.account_type,
            mtd_spend=mtd_spend,
            forecast_spend=forecast_spend,
            monthly_budget=bundle.monthly_budget,
            currency=currency,
            billing_period=billing_period,
            is_budget_exceeded=is_exceeded,
            recorded_at=now,
        )

    async def get_billing_summary(
        self,
        bundle: OCIClientBundle,
        current_time: Optional[datetime] = None,
    ) -> BillingSummary:
        """Asynchronously retrieve MTD spend and calculate linear run-rate forecast.

        Args:
            bundle: Target account OCI client bundle.
            current_time: Optional reference datetime (defaults to current UTC).

        Returns:
            BillingSummary containing MTD spend, projected forecast, and budget alert flag.
        """
        return await asyncio.to_thread(
            self._sync_get_billing_summary, bundle, current_time
        )
