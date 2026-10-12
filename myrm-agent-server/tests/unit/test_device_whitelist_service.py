"""Unit tests for ContainerDeviceWhitelistService in server layer.

Verifies service orchestration, device inspection, batch sanitization with block device stripping,
cgroup device rules generation, and policy configuration updates.
Strict typing applied: No `Any` types allowed. Enforced under 400 lines limit.
"""

from __future__ import annotations

import pytest

from app.schemas.device_whitelist import (
    DeviceInspectRequest,
    DevicePolicyConfigRequest,
    DeviceSanitizeRequest,
)
from app.services.security.device_whitelist_service import (
    ContainerDeviceWhitelistService,
)


@pytest.fixture(autouse=True)
def clean_service_instance() -> None:
    ContainerDeviceWhitelistService.reset_instance()
    yield
    ContainerDeviceWhitelistService.reset_instance()


def test_inspect_device_virtual_and_block() -> None:
    service = ContainerDeviceWhitelistService.get_instance()

    # 1. Standard virtual device -> ALLOW
    res_null = service.inspect_device(DeviceInspectRequest(device_path="/dev/null"))
    assert res_null.action == "ALLOW"
    assert res_null.matched_rule == "ALLOWED_VIRTUAL_DEVICE"
    assert res_null.device_type == "c"

    # 2. Physical block device -> STRIP
    res_sda = service.inspect_device(DeviceInspectRequest(device_path="/dev/sda1"))
    assert res_sda.action == "STRIP"
    assert res_sda.matched_rule == "STRIPPED_PHYSICAL_BLOCK_DEVICE"
    assert res_sda.device_type == "b"

    # 3. Host hardware device -> STRIP
    res_mem = service.inspect_device(DeviceInspectRequest(device_path="/dev/mem"))
    assert res_mem.action == "STRIP"
    assert res_mem.matched_rule == "STRIPPED_HOST_HARDWARE_DEVICE"


def test_sanitize_device_list_service() -> None:
    service = ContainerDeviceWhitelistService.get_instance()

    batch_req = DeviceSanitizeRequest(
        devices=[
            "/dev/zero",
            "/dev/sda",
            "/dev/random",
            "/dev/loop0",
            "/dev/kmsg",
        ]
    )
    report = service.sanitize_device_list(batch_req)
    assert report.total_inspected == 5
    assert report.is_fully_compliant is False
    assert set(report.allowed_devices) == {"/dev/zero", "/dev/random"}
    assert set(report.stripped_devices) == {"/dev/sda", "/dev/loop0", "/dev/kmsg"}
    assert len(report.reasons) == 3


def test_cgroup_rules_and_standard_devices_service() -> None:
    service = ContainerDeviceWhitelistService.get_instance()

    # Cgroup rules
    cg_res = service.get_cgroup_rules()
    assert len(cg_res.cgroup_rules) >= 7
    assert any("c 1:3 rwm" in r for r in cg_res.cgroup_rules)
    assert any("--device-cgroup-rule=c 1:3 rwm" == a for a in cg_res.docker_device_args)
    # Ensure no block device is permitted
    for r in cg_res.cgroup_rules:
        assert not r.startswith("b ")

    # Standard devices
    devs = service.get_standard_virtual_devices()
    assert len(devs) >= 7
    paths = {d.path for d in devs}
    assert "/dev/null" in paths
    assert "/dev/zero" in paths
    assert "/dev/urandom" in paths


def test_policy_get_and_update_service() -> None:
    service = ContainerDeviceWhitelistService.get_instance()

    default_policy = service.get_policy()
    assert default_policy.strict_minimal_allowlist is True
    assert default_policy.strip_block_devices is True

    update_req = DevicePolicyConfigRequest(
        strict_minimal_allowlist=True,
        strip_block_devices=True,
        strip_host_hardware_devices=True,
        custom_allowed_devices=["/dev/custom_device"],
    )
    updated_policy = service.update_policy(update_req)
    assert updated_policy.custom_allowed_devices == ["/dev/custom_device"]

    # Verify custom device is now allowed
    res_custom = service.inspect_device(DeviceInspectRequest(device_path="/dev/custom_device"))
    assert res_custom.action == "ALLOW"
    assert res_custom.matched_rule == "ALLOWED_VIRTUAL_DEVICE"
