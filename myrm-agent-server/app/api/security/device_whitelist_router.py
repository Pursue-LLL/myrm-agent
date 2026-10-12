"""REST API Router for Sandbox Container Device Whitelist Hardening
and Block Device Strip Suite.

[INPUT]
- fastapi::APIRouter, Depends, status
- app.schemas.device_whitelist::(CgroupRulesResponse, DeviceInspectRequest, DeviceInspectResponse,
  DevicePolicyConfigRequest, DevicePolicyConfigResponse, DeviceSanitizeRequest,
  DeviceSanitizeResponse, VirtualDeviceSpecSchema)
- app.services.security.device_whitelist_service::ContainerDeviceWhitelistService

[OUTPUT]
- device_whitelist_router: mounted FastAPI APIRouter

[POS]
REST API interface for container device validation, block device stripping, and cgroup rules.
Strictly avoids Any types; enforced under 400 lines limit.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

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
from app.services.security.device_whitelist_service import (
    ContainerDeviceWhitelistService,
)

device_whitelist_router = APIRouter(
    prefix="/device-whitelist",
    tags=["Container Device Whitelist"],
)


def get_device_service() -> ContainerDeviceWhitelistService:
    """Dependency provider for ContainerDeviceWhitelistService."""
    return ContainerDeviceWhitelistService.get_instance()


@device_whitelist_router.post(
    "/inspect",
    response_model=DeviceInspectResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect a single device node candidate",
)
async def inspect_device(
    request: DeviceInspectRequest,
    service: ContainerDeviceWhitelistService = Depends(get_device_service),
) -> DeviceInspectResponse:
    """Evaluate whether a device node is an authorized virtual device or dangerous block device."""
    return service.inspect_device(request)


@device_whitelist_router.post(
    "/sanitize",
    response_model=DeviceSanitizeResponse,
    status_code=status.HTTP_200_OK,
    summary="Sanitize a collection of device nodes and strip dangerous devices",
)
async def sanitize_device_list(
    request: DeviceSanitizeRequest,
    service: ContainerDeviceWhitelistService = Depends(get_device_service),
) -> DeviceSanitizeResponse:
    """Filter out physical block devices and host hardware from container configuration."""
    return service.sanitize_device_list(request)


@device_whitelist_router.get(
    "/cgroup-rules",
    response_model=CgroupRulesResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate cgroup device permission rules and Docker CLI flags",
)
async def get_cgroup_rules(
    service: ContainerDeviceWhitelistService = Depends(get_device_service),
) -> CgroupRulesResponse:
    """Retrieve hardened cgroup device rules strictly denying block devices."""
    return service.get_cgroup_rules()


@device_whitelist_router.get(
    "/standard-devices",
    response_model=list[VirtualDeviceSpecSchema],
    status_code=status.HTTP_200_OK,
    summary="List standard authorized virtual pseudo-devices",
)
async def get_standard_virtual_devices(
    service: ContainerDeviceWhitelistService = Depends(get_device_service),
) -> list[VirtualDeviceSpecSchema]:
    """Retrieve the 6 core standard safe pseudo-devices aligned with CodePilot."""
    return service.get_standard_virtual_devices()


@device_whitelist_router.get(
    "/policy",
    response_model=DevicePolicyConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve current container device policy configuration",
)
async def get_policy(
    service: ContainerDeviceWhitelistService = Depends(get_device_service),
) -> DevicePolicyConfigResponse:
    """Retrieve active device allowlist and block stripping policy."""
    return service.get_policy()


@device_whitelist_router.put(
    "/policy",
    response_model=DevicePolicyConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Update container device policy configuration",
)
async def update_policy(
    request: DevicePolicyConfigRequest,
    service: ContainerDeviceWhitelistService = Depends(get_device_service),
) -> DevicePolicyConfigResponse:
    """Update device policy settings."""
    return service.update_policy(request)
