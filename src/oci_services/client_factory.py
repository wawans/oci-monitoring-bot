"""OCI Multi-Account Client Factory and credential handshake verification."""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import oci
from oci.core import ComputeClient, VirtualNetworkClient
from oci.monitoring import MonitoringClient
from oci.usage_api import UsageapiClient

from config.parser import AccountConfig, AccountType

logger = logging.getLogger(__name__)


@dataclass
class OCIClientBundle:
    """Container holding all initialized OCI SDK clients for a single tenancy/account."""

    account_id: str
    account_name: str
    account_type: AccountType
    compartment_id: str
    region: str
    monthly_budget: float
    compute_client: ComputeClient
    network_client: VirtualNetworkClient
    monitoring_client: MonitoringClient
    usage_client: UsageapiClient
    raw_config: Dict[str, Any]


class ClientInitializationError(Exception):
    """Raised when an OCI client bundle cannot be created."""


class OCIClientFactory:
    """Factory responsible for lifecycle and retrieval of per-account OCI SDK clients."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir: Optional[Path] = base_dir
        self._bundles: Dict[str, OCIClientBundle] = {}

    @property
    def bundles(self) -> Dict[str, OCIClientBundle]:
        """Return all initialized client bundles."""
        return self._bundles

    def get_bundle(self, account_id: str) -> Optional[OCIClientBundle]:
        """Retrieve client bundle for a given account_id, or None if not registered."""
        return self._bundles.get(account_id)

    def get_all_bundles(self) -> List[OCIClientBundle]:
        """Return list of all registered client bundles."""
        return list(self._bundles.values())

    def create_bundle(self, account: AccountConfig) -> OCIClientBundle:
        """Create and validate OCI clients for a single AccountConfig.

        Args:
            account: AccountConfig instance to build clients for.

        Returns:
            OCIClientBundle containing initialized OCI SDK clients.

        Raises:
            ClientInitializationError: If config dictionary is invalid or key is missing.
        """
        if not account.validate_key_file_exists(self.base_dir):
            resolved_key = account.resolve_key_path(self.base_dir)
            raise ClientInitializationError(
                f"Private key file not found for account '{account.account_id}': {resolved_key}"
            )

        oci_config = account.to_oci_config_dict(self.base_dir)

        try:
            oci.config.validate_config(oci_config)
        except Exception as e:
            raise ClientInitializationError(
                f"OCI config validation failed for account '{account.account_id}': {e}"
            ) from e

        try:
            compute_client = ComputeClient(oci_config)
            network_client = VirtualNetworkClient(oci_config)
            monitoring_client = MonitoringClient(oci_config)
            usage_client = UsageapiClient(oci_config)

            bundle = OCIClientBundle(
                account_id=account.account_id,
                account_name=account.name,
                account_type=account.account_type,
                compartment_id=account.compartment_id,
                region=account.region,
                monthly_budget=account.monthly_budget,
                compute_client=compute_client,
                network_client=network_client,
                monitoring_client=monitoring_client,
                usage_client=usage_client,
                raw_config=oci_config,
            )
            return bundle
        except Exception as e:
            raise ClientInitializationError(
                f"Failed to instantiate OCI clients for account '{account.account_id}': {e}"
            ) from e

    def initialize_clients(self, accounts: List[AccountConfig]) -> Dict[str, OCIClientBundle]:
        """Initialize clients for all active accounts with per-account fault isolation.

        Kegagalan pada salah satu akun tidak boleh menghentikan pemrosesan akun lainnya.

        Args:
            accounts: List of account configurations.

        Returns:
            Dictionary mapping account_id to successfully initialized OCIClientBundle.
        """
        self._bundles.clear()

        for account in accounts:
            if not account.is_active:
                logger.info("Skipping inactive account: %s (%s)", account.account_id, account.name)
                continue

            try:
                bundle = self.create_bundle(account)
                self._bundles[account.account_id] = bundle
                logger.info(
                    "Successfully initialized OCI client bundle for account: %s (%s)",
                    account.account_id,
                    account.name,
                )
            except Exception as e:
                # Fault isolation: log and continue to next account
                logger.error(
                    "Failed to initialize OCI clients for account %s (%s): %s",
                    account.account_id,
                    account.name,
                    e,
                )

        return self._bundles

    async def verify_handshake(self, account_id: str) -> bool:
        """Verify API connectivity and credentials for an account asynchronously.

        Args:
            account_id: Target account identifier.

        Returns:
            True if authentication handshake succeeds, False otherwise.
        """
        bundle = self.get_bundle(account_id)
        if not bundle:
            logger.warning("Cannot verify handshake: unknown account_id '%s'", account_id)
            return False

        def _sync_check() -> bool:
            try:
                # Perform a lightweight call (list instances with limit 1)
                bundle.compute_client.list_instances(
                    compartment_id=bundle.compartment_id,
                    limit=1,
                )
                return True
            except Exception as e:
                logger.warning(
                    "Handshake failed for account %s (%s): %s",
                    bundle.account_id,
                    bundle.account_name,
                    e,
                )
                return False

        return await asyncio.to_thread(_sync_check)

    async def verify_all_handshakes(self) -> Dict[str, bool]:
        """Perform handshake verification across all registered accounts concurrently.

        Returns:
            Dictionary mapping account_id to boolean handshake status.
        """
        results: Dict[str, bool] = {}
        tasks = [
            (acc_id, self.verify_handshake(acc_id))
            for acc_id in self._bundles
        ]

        for acc_id, task in tasks:
            results[acc_id] = await task

        return results
