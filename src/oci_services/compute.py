"""OCI Compute and VNIC IP Resolution Service."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from src.oci_services.client_factory import OCIClientBundle

logger = logging.getLogger(__name__)


class ComputeServiceError(Exception):
    """Base exception for compute-related operations."""


class ComputeActionError(ComputeServiceError):
    """Raised when an instance power action fails."""


@dataclass
class InstanceInfo:
    """Representation of an OCI compute instance with resolved network properties."""

    instance_id: str
    account_id: str
    region: str
    compartment_id: str
    display_name: str
    shape: str
    lifecycle_state: str
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None


class ComputeService:
    """Service handling compute instance discovery, IP resolution, and power actions."""

    VALID_ACTIONS = {"START", "STOP", "SOFTRESET"}

    @staticmethod
    def _sync_resolve_ips(
        bundle: OCIClientBundle, instance_id: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Synchronously query VNIC attachments and extract public/private IP addresses."""
        try:
            attachments_response = bundle.compute_client.list_vnic_attachments(
                compartment_id=bundle.compartment_id,
                instance_id=instance_id,
            )
            attachments = attachments_response.data or []

            for attachment in attachments:
                if attachment.lifecycle_state == "ATTACHED" and attachment.vnic_id:
                    vnic_response = bundle.network_client.get_vnic(attachment.vnic_id)
                    vnic = vnic_response.data
                    if vnic:
                        public_ip = getattr(vnic, "public_ip", None)
                        private_ip = getattr(vnic, "private_ip", None)
                        return public_ip, private_ip

            return None, None
        except Exception as e:
            logger.warning(
                "Failed to resolve VNIC IP for instance %s on account %s: %s",
                instance_id,
                bundle.account_id,
                e,
            )
            return None, None

    async def resolve_instance_ips(
        self, bundle: OCIClientBundle, instance_id: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Asynchronously resolve Public IP and Private IP for an instance."""
        return await asyncio.to_thread(self._sync_resolve_ips, bundle, instance_id)

    async def list_instances(
        self,
        bundle: OCIClientBundle,
        include_terminated: bool = False,
        resolve_ips: bool = True,
    ) -> List[InstanceInfo]:
        """List compute instances in the bundle's compartment and optionally resolve their IPs.

        Args:
            bundle: Target account OCI client bundle.
            include_terminated: Whether to include TERMINATED instances. Defaults to False.
            resolve_ips: Whether to resolve public/private IPs for each instance.

        Returns:
            List of InstanceInfo dataclass instances.
        """
        def _sync_list() -> List[Any]:
            response = bundle.compute_client.list_instances(
                compartment_id=bundle.compartment_id
            )
            return response.data or []

        try:
            raw_instances = await asyncio.to_thread(_sync_list)
        except Exception as e:
            logger.error(
                "Error listing instances for account %s (%s): %s",
                bundle.account_id,
                bundle.account_name,
                e,
            )
            raise ComputeServiceError(f"Failed to list instances for {bundle.account_id}: {e}") from e

        results: List[InstanceInfo] = []
        for raw_vm in raw_instances:
            lifecycle = getattr(raw_vm, "lifecycle_state", "UNKNOWN")
            if not include_terminated and lifecycle in {"TERMINATED", "TERMINATING"}:
                continue

            instance_id = raw_vm.id
            public_ip: Optional[str] = None
            private_ip: Optional[str] = None

            if resolve_ips and lifecycle not in {"TERMINATED", "TERMINATING"}:
                public_ip, private_ip = await self.resolve_instance_ips(bundle, instance_id)

            info = InstanceInfo(
                instance_id=instance_id,
                account_id=bundle.account_id,
                region=bundle.region,
                compartment_id=bundle.compartment_id,
                display_name=getattr(raw_vm, "display_name", instance_id),
                shape=getattr(raw_vm, "shape", "Unknown"),
                lifecycle_state=lifecycle,
                public_ip=public_ip,
                private_ip=private_ip,
            )
            results.append(info)

        return results

    async def get_instance(
        self,
        bundle: OCIClientBundle,
        instance_id: str,
        resolve_ips: bool = True,
    ) -> Optional[InstanceInfo]:
        """Retrieve details and network info for a single compute instance."""
        def _sync_get() -> Any:
            try:
                response = bundle.compute_client.get_instance(instance_id=instance_id)
                return response.data
            except Exception as e:
                logger.warning(
                    "Could not fetch instance %s on account %s: %s",
                    instance_id,
                    bundle.account_id,
                    e,
                )
                return None

        raw_vm = await asyncio.to_thread(_sync_get)
        if not raw_vm:
            return None

        public_ip: Optional[str] = None
        private_ip: Optional[str] = None
        lifecycle = getattr(raw_vm, "lifecycle_state", "UNKNOWN")

        if resolve_ips and lifecycle not in {"TERMINATED", "TERMINATING"}:
            public_ip, private_ip = await self.resolve_instance_ips(bundle, instance_id)

        return InstanceInfo(
            instance_id=raw_vm.id,
            account_id=bundle.account_id,
            region=bundle.region,
            compartment_id=bundle.compartment_id,
            display_name=getattr(raw_vm, "display_name", raw_vm.id),
            shape=getattr(raw_vm, "shape", "Unknown"),
            lifecycle_state=lifecycle,
            public_ip=public_ip,
            private_ip=private_ip,
        )

    async def execute_action(
        self,
        bundle: OCIClientBundle,
        instance_id: str,
        action: str,
    ) -> bool:
        """Execute a power management action on a compute instance.

        Supported actions: START, STOP, SOFTRESET.

        Args:
            bundle: Target account OCI client bundle.
            instance_id: OCID of the target compute instance.
            action: Power action string (START, STOP, SOFTRESET).

        Returns:
            True if action was accepted by OCI, False otherwise.

        Raises:
            ComputeActionError: If action is invalid or OCI API rejects the request.
        """
        normalized_action = action.upper().strip()
        if normalized_action not in self.VALID_ACTIONS:
            raise ComputeActionError(
                f"Invalid compute action '{action}'. Supported: {', '.join(sorted(self.VALID_ACTIONS))}"
            )

        def _sync_action() -> bool:
            try:
                logger.info(
                    "Executing %s action on instance %s (Account: %s)",
                    normalized_action,
                    instance_id,
                    bundle.account_id,
                )
                bundle.compute_client.instance_action(
                    instance_id=instance_id,
                    action=normalized_action,
                )
                return True
            except Exception as e:
                logger.error(
                    "Failed executing %s on instance %s (Account: %s): %s",
                    normalized_action,
                    instance_id,
                    bundle.account_id,
                    e,
                )
                raise ComputeActionError(
                    f"OCI API rejected {normalized_action} for {instance_id}: {e}"
                ) from e

        return await asyncio.to_thread(_sync_action)
