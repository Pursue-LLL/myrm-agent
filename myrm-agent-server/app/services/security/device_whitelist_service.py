"""Service layer for Sandbox Container Device Whitelist Hardening
and Block Device Strip Suite.

[INPUT]
- app.schemas.device_whitelist::(CgroupRulesResponse, DeviceInspectRequest, DeviceInspectResponse,
  DevicePolicyConfigRequest, DevicePolicyConfigResponse, DeviceSanitizeRequest,
  DeviceSanitizeResponse, VirtualDeviceSpecSchema)
- myrm_agent_harness.core.security.device_whitelist::(ContainerDevicePolicyConfig,
  ContainerDeviceWhitelistFacade)
- stdlib threading

[OUTPUT]
- ContainerDeviceWhitelistService: singleton service managing device inspection,
  block device stripping, and cgroup rules generation

[POS]
Service layer bridging REST API endpoints to harness ContainerDeviceWhitelistFacade.
Strictly avoids Any types; enforced under 400 lines limit.
"""

from __future__ import annotations

import threading

from myrm_agent_harness.core.security.device_whitelist import (
    ContainerDevicePolicyConfig,
    ContainerDeviceWhitelistFacade,
)

from app.schemas.device_whitelist import (
    CgroupRulesResponse,
    DeviceInspectRequest,
    DeviceInspectResponse,
    DevicePolicyConfigRequest,
    DevicePolicyConfigResponse,
    DeviceSanitizeRequest,
    DeviceSanitizeResponse,
    VirtualDeviceSpecSchema,
)


class ContainerDeviceWhitelistService:
    """Singleton service orchestrating container device allowlisting and block device stripping."""

    _instance: ContainerDeviceWhitelistService | None = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._facade: ContainerDeviceWhitelistFacade = ContainerDeviceWhitelistFacade()

    @classmethod
    def get_instance(cls) -> ContainerDeviceWhitelistService:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            cls._instance = None

    def inspect_device(self, request: DeviceInspectRequest) -> DeviceInspectResponse:
        """Inspect a single device path candidate."""
        res = self._facade.inspect_device(request.device_path)
        return DeviceInspectResponse(
            path=res.path,
            action=res.action.value,
            device_type=res.device_type.value if res.device_type is not None else None,
            matched_rule=res.matched_rule,
            reason=res.reason,
        )

    def sanitize_device_list(self, request: DeviceSanitizeRequest) -> DeviceSanitizeResponse:
        """Sanitize a list of container device nodes and strip dangerous devices."""
        report = self._facade.sanitize_device_list(request.devices)
        return DeviceSanitizeResponse(
            total_inspected=report.total_inspected,
            allowed_devices=list(report.allowed_devices),
            stripped_devices=list(report.stripped_devices),
            reasons=list(report.reasons),
            is_fully_compliant=report.is_fully_compliant,
        )

    def get_cgroup_rules(self) -> CgroupRulesResponse:
        """Generate cgroup device permission rules and Docker CLI arguments."""
        rules = self._facade.get_cgroup_device_rules()
        docker_args = self._facade.get_docker_device_args()
        return CgroupRulesResponse(
            cgroup_rules=rules,
            docker_device_args=docker_args,
        )

    def get_standard_virtual_devices(self) -> list[VirtualDeviceSpecSchema]:
        """List standard authorized virtual pseudo-devices."""
        devs = self._facade.get_standard_virtual_devices()
        return [
            VirtualDeviceSpecSchema(
                path=d.path,
                major=d.major,
                minor=d.minor,
                device_type=d.device_type.value,
                permissions=d.permissions,
                description=d.description,
            )
            for d in devs
        ]

    def get_policy(self) -> DevicePolicyConfigResponse:
        """Retrieve active container device policy settings."""
        cfg = self._facade.config
        return DevicePolicyConfigResponse(
            strict_minimal_allowlist=cfg.strict_minimal_allowlist,
            strip_block_devices=cfg.strip_block_devices,
            strip_host_hardware_devices=cfg.strip_host_hardware_devices,
            custom_allowed_devices=list(cfg.custom_allowed_devices),
        )

    def update_policy(self, request: DevicePolicyConfigRequest) -> DevicePolicyConfigResponse:
        """Update container device policy settings."""
        new_cfg = ContainerDevicePolicyConfig(
            strict_minimal_allowlist=request.strict_minimal_allowlist,
            strip_block_devices=request.strip_block_devices,
            strip_host_hardware_devices=request.strip_host_hardware_devices,
            custom_allowed_devices=tuple(request.custom_allowed_devices),
        )
        self._facade.update_config(new_cfg)
        return self.get_policy()
