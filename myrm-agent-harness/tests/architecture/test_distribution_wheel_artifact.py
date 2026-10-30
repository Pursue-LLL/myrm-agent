"""Architecture gate: release/core wheel zip contents must not leak manifest source."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_ARCH_DIR))

from distribution_wheel_helpers import (
    ELF_ARM64,
    ELF_X64,
    MACHO_ARM64,
    MACHO_X64,
    PE_X64,
    elf_header,
    fat_macho_header,
    macho_header,
    pe_header,
    stub_compiled_artifact_path,
    write_minimal_core_wheel,
    write_minimal_release_wheel,
)

from harness_packaging.integrity import (
    DistributionWheelArtifactError,
    DistributionWheelRole,
    distribution_wheel_artifact_violations,
    verify_distribution_wheel_artifact,
)
from harness_packaging.platforms import ALL_PLATFORMS, platform_spec_for_key
from harness_packaging.release import finalize_stripped_release_wheel, manifest_source_paths


def _assert_wheel_record_matches_archive(wheel_path: Path) -> None:
    with zipfile.ZipFile(wheel_path, "r") as zf:
        record_path = next(name for name in zf.namelist() if name.endswith(".dist-info/RECORD"))
        archive_paths = set(zf.namelist())
        recorded_paths: set[str] = set()

        for line in zf.read(record_path).decode("utf-8").splitlines():
            if not line:
                continue
            path, digest, size_str = line.split(",", 2)
            recorded_paths.add(path)
            if path == record_path:
                assert digest == ""
                assert size_str == ""
                continue
            assert path in archive_paths
            data = zf.read(path)
            assert int(size_str) == len(data)
            assert digest.startswith("sha256=")

        assert recorded_paths == archive_paths


@pytest.mark.architecture
def test_release_wheel_artifact_accepts_stripped_layout(tmp_path: Path) -> None:
    wheel_path = tmp_path / "myrm_agent_harness-0.1.0-py3-none-any.whl"
    write_minimal_release_wheel(wheel_path)
    verify_distribution_wheel_artifact(wheel_path, role=DistributionWheelRole.RELEASE)


@pytest.mark.architecture
def test_release_wheel_artifact_rejects_manifest_py(tmp_path: Path) -> None:
    manifest_paths = manifest_source_paths()
    wheel_path = tmp_path / "myrm_agent_harness-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr("myrm_agent_harness/api/__init__.py", "# public")
        zf.writestr(manifest_paths[0], "# secret")

    violations = distribution_wheel_artifact_violations(
        wheel_path,
        role=DistributionWheelRole.RELEASE,
    )
    assert violations
    assert "Manifest .py source must not ship" in violations[0]

    with pytest.raises(DistributionWheelArtifactError, match=r"Manifest \.py source must not ship"):
        verify_distribution_wheel_artifact(wheel_path, role=DistributionWheelRole.RELEASE)


@pytest.mark.architecture
def test_release_wheel_artifact_rejects_debug_map(tmp_path: Path) -> None:
    wheel_path = tmp_path / "myrm_agent_harness-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr("myrm_agent_harness/api/__init__.py", "# public")
        zf.writestr("myrm_agent_harness/cli.js.map", "{}")

    with pytest.raises(DistributionWheelArtifactError, match="Debug mapping artifacts"):
        verify_distribution_wheel_artifact(wheel_path, role=DistributionWheelRole.RELEASE)


@pytest.mark.architecture
def test_release_wheel_artifact_rejects_invalid_zip(tmp_path: Path) -> None:
    wheel_path = tmp_path / "myrm_agent_harness-0.1.0-py3-none-any.whl"
    wheel_path.write_bytes(b"not-a-wheel")

    with pytest.raises(DistributionWheelArtifactError, match="Invalid wheel zip"):
        verify_distribution_wheel_artifact(wheel_path, role=DistributionWheelRole.RELEASE)


@pytest.mark.architecture
def test_core_wheel_artifact_accepts_compiled_layout(tmp_path: Path) -> None:
    wheel_path = tmp_path / "myrm_agent_harness_core_linux_x64-0.1.0-cp313-cp313-linux_x86_64.whl"
    write_minimal_core_wheel(wheel_path)
    verify_distribution_wheel_artifact(wheel_path, role=DistributionWheelRole.CORE)


@pytest.mark.architecture
def test_finalize_stripped_release_wheel_strips_and_verifies(tmp_path: Path) -> None:
    manifest_paths = manifest_source_paths()
    wheel_path = tmp_path / "myrm_agent_harness-0.1.0-py3-none-any.whl"
    record_path = "myrm_agent_harness-0.1.0.dist-info/RECORD"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr("myrm_agent_harness/api/__init__.py", "# public")
        for manifest_path in manifest_paths[:2]:
            zf.writestr(manifest_path, "# secret")
        zf.writestr(
            record_path,
            "\n".join(
                [
                    "myrm_agent_harness/api/__init__.py,sha256=deadbeef,7",
                    f"{manifest_paths[0]},sha256=deadbeef,8",
                    f"{manifest_paths[1]},sha256=deadbeef,8",
                    f"{record_path},,",
                ]
            )
            + "\n",
        )

    result = finalize_stripped_release_wheel(wheel_path, in_place=True)
    assert result == wheel_path

    with zipfile.ZipFile(wheel_path, "r") as zf:
        names = zf.namelist()
    assert "myrm_agent_harness/api/__init__.py" in names
    assert manifest_paths[0] not in names
    assert manifest_paths[1] not in names
    _assert_wheel_record_matches_archive(wheel_path)


@pytest.mark.architecture
def test_finalize_stripped_release_wheel_rebuilds_record_with_dist_info(tmp_path: Path) -> None:
    manifest_paths = manifest_source_paths()
    wheel_path = tmp_path / "myrm_agent_harness-0.1.0-py3-none-any.whl"
    record_path = "myrm_agent_harness-0.1.0.dist-info/RECORD"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr("myrm_agent_harness/api/__init__.py", "# public")
        zf.writestr(manifest_paths[0], "# secret")
        zf.writestr(
            record_path,
            "\n".join(
                [
                    "myrm_agent_harness/api/__init__.py,sha256=deadbeef,7",
                    f"{manifest_paths[0]},sha256=deadbeef,8",
                    f"{record_path},,",
                ]
            )
            + "\n",
        )

    finalize_stripped_release_wheel(wheel_path, in_place=True)
    _assert_wheel_record_matches_archive(wheel_path)


@pytest.mark.architecture
def test_core_wheel_artifact_rejects_manifest_py_and_missing_compiled(tmp_path: Path) -> None:
    manifest_paths = manifest_source_paths()
    wheel_path = tmp_path / "myrm_agent_harness_core_linux_x64-0.1.0-cp313-cp313-linux_x86_64.whl"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr(manifest_paths[0], "# secret")

    violations = distribution_wheel_artifact_violations(
        wheel_path,
        role=DistributionWheelRole.CORE,
    )
    assert any("Manifest .py source must not ship" in item for item in violations)
    assert any("Missing Nuitka .so/.pyd" in item for item in violations)


@pytest.mark.architecture
def test_core_wheel_artifact_rejects_unknown_platform_key(tmp_path: Path) -> None:
    manifest_paths = manifest_source_paths()
    wheel_path = tmp_path / "myrm_agent_harness_core_linux_x64-0.1.0-cp313-cp313-linux_x86_64.whl"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr(
            "myrm_agent_harness_core/__init__.py",
            '__platform_key__: str = "unknown"\n',
        )
        for manifest_py in manifest_paths[:1]:
            zf.writestr(stub_compiled_artifact_path(manifest_py), b"")

    violations = distribution_wheel_artifact_violations(
        wheel_path,
        role=DistributionWheelRole.CORE,
    )
    assert any("platform key is still 'unknown'" in item for item in violations)

    with pytest.raises(DistributionWheelArtifactError, match="platform key is still 'unknown'"):
        verify_distribution_wheel_artifact(wheel_path, role=DistributionWheelRole.CORE)


@pytest.mark.architecture
def test_core_wheel_artifact_rejects_missing_core_package_init(tmp_path: Path) -> None:
    manifest_paths = manifest_source_paths()
    wheel_path = tmp_path / "myrm_agent_harness_core_linux_x64-0.1.0-cp313-cp313-linux_x86_64.whl"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        for manifest_py in manifest_paths[:1]:
            zf.writestr(stub_compiled_artifact_path(manifest_py), b"")

    violations = distribution_wheel_artifact_violations(
        wheel_path,
        role=DistributionWheelRole.CORE,
    )
    assert any("missing myrm_agent_harness_core/__init__.py" in item for item in violations)


def _core_wheel_path(tmp_path: Path, platform_key: str) -> Path:
    return tmp_path / f"myrm_agent_harness_core_{platform_key.replace('-', '_')}-0.1.0-py3-none-any.whl"


@pytest.mark.architecture
@pytest.mark.parametrize("platform_key", ALL_PLATFORMS)
def test_core_wheel_artifact_accepts_native_code_for_every_platform_key(tmp_path: Path, platform_key: str) -> None:
    wheel_path = _core_wheel_path(tmp_path, platform_key)
    write_minimal_core_wheel(wheel_path, platform_key)
    assert distribution_wheel_artifact_violations(wheel_path, role=DistributionWheelRole.CORE) == ()


@pytest.mark.architecture
@pytest.mark.parametrize(
    ("platform_key", "binary", "found"),
    [
        ("darwin-x64", macho_header(MACHO_ARM64), "arm64"),
        ("win32-arm64", pe_header(PE_X64), "x64"),
        ("darwin-arm64", macho_header(MACHO_X64), "x64"),
        ("linux-x64", elf_header(ELF_ARM64), "arm64"),
        ("linux-arm64-musl", elf_header(ELF_X64), "x64"),
    ],
)
def test_core_wheel_artifact_rejects_code_built_for_another_cpu(
    tmp_path: Path, platform_key: str, binary: bytes, found: str
) -> None:
    """Nuitka cannot cross-compile, so a wheel stamped for one CPU but built on another holds host code."""
    wheel_path = _core_wheel_path(tmp_path, platform_key)
    write_minimal_core_wheel(wheel_path, platform_key, binary=binary)
    machine = platform_spec_for_key(platform_key).machine

    violations = distribution_wheel_artifact_violations(wheel_path, role=DistributionWheelRole.CORE)

    assert len(violations) == 1
    assert violations[0].startswith(f"Compiled modules must hold {machine} code for platform key {platform_key}: ")
    assert f"({found})" in violations[0]
    assert "more)" in violations[0], "a wheel of wrong modules names a few of them and counts the rest"
    with pytest.raises(
        DistributionWheelArtifactError, match=f"must hold {machine} code for platform key {platform_key}"
    ):
        verify_distribution_wheel_artifact(wheel_path, role=DistributionWheelRole.CORE)


@pytest.mark.architecture
def test_core_wheel_artifact_rejects_a_compiled_module_that_is_no_native_binary(tmp_path: Path) -> None:
    wheel_path = _core_wheel_path(tmp_path, "linux-x64")
    write_minimal_core_wheel(wheel_path, "linux-x64", binary=b"")

    violations = distribution_wheel_artifact_violations(wheel_path, role=DistributionWheelRole.CORE)

    assert len(violations) == 1
    assert "(not an x64/arm64 binary)" in violations[0]


@pytest.mark.architecture
def test_core_wheel_artifact_accepts_a_universal_binary_that_holds_the_key_cpu(tmp_path: Path) -> None:
    both = _core_wheel_path(tmp_path / "both", "darwin-x64")
    arm_only = _core_wheel_path(tmp_path / "arm-only", "darwin-x64")
    for path in (both, arm_only):
        path.parent.mkdir()
    write_minimal_core_wheel(both, "darwin-x64", binary=fat_macho_header(MACHO_ARM64, MACHO_X64))
    write_minimal_core_wheel(arm_only, "darwin-x64", binary=fat_macho_header(MACHO_ARM64))

    assert distribution_wheel_artifact_violations(both, role=DistributionWheelRole.CORE) == ()
    assert distribution_wheel_artifact_violations(arm_only, role=DistributionWheelRole.CORE)


@pytest.mark.architecture
@pytest.mark.parametrize(
    ("init_text", "expected"),
    [
        ('__version__ = "0.1.0"\n', "does not stamp __platform_key__"),
        ('__platform_key__: str = "darwin-riscv64"\n', "'darwin-riscv64' is not a platform the release builds"),
    ],
    ids=["no-stamp", "unknown-key"],
)
def test_core_wheel_artifact_rejects_a_platform_stamp_it_cannot_check_binaries_against(
    tmp_path: Path, init_text: str, expected: str
) -> None:
    wheel_path = _core_wheel_path(tmp_path, "linux-x64")
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr("myrm_agent_harness_core/__init__.py", init_text)
        for manifest_py in manifest_source_paths():
            zf.writestr(stub_compiled_artifact_path(manifest_py), elf_header(ELF_X64))

    violations = distribution_wheel_artifact_violations(wheel_path, role=DistributionWheelRole.CORE)

    assert len(violations) == 1
    assert expected in violations[0]
