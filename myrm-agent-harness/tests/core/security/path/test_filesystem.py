"""Generic filesystem path safety — dangerous roots, device names, boundary, safe join, coercion.

Mirrors `core.security.path.filesystem`; protection policy lives in `test_rules`.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.core.security.path import (
    BLOCKED_DEVICE_NAMES,
    DANGEROUS_PATHS,
    coerce_filesystem_path,
    covers_dangerous_path,
    is_blocked_device_path,
    is_dangerous_path,
    safe_join_path,
)


class TestCoerceFilesystemPath:
    """Test coerce_filesystem_path() runtime type guard."""

    def test_none_and_empty_string(self) -> None:
        assert coerce_filesystem_path(None) is None
        assert coerce_filesystem_path("") is None
        assert coerce_filesystem_path("   ") is None

    def test_str_and_path(self) -> None:
        assert coerce_filesystem_path("/tmp/ws") == Path("/tmp/ws")
        assert coerce_filesystem_path(Path("/tmp/ws")) == Path("/tmp/ws")

    def test_rejects_magicmock_and_arbitrary_objects(self) -> None:
        assert coerce_filesystem_path(MagicMock()) is None
        assert coerce_filesystem_path(123) is None
        assert coerce_filesystem_path(["/tmp/ws"]) is None

class TestDangerousPaths:
    """Verify DANGEROUS_PATHS contains expected entries."""

    def test_unix_system_roots_present(self) -> None:
        for path in ("/etc", "/sys", "/proc", "/dev", "/root", "/boot", "/var/log"):
            real = os.path.realpath(path)
            assert real in DANGEROUS_PATHS, f"{path} (resolved: {real}) not in DANGEROUS_PATHS"

    def test_user_sensitive_dirs_present(self) -> None:
        for path in ("~/.ssh", "~/.gnupg", "~/.aws", "~/.docker", "~/.kube"):
            real = os.path.realpath(os.path.expanduser(path))
            assert real in DANGEROUS_PATHS, f"{path} (resolved: {real}) not in DANGEROUS_PATHS"

    def test_docker_and_kube_included(self) -> None:
        docker_real = os.path.realpath(os.path.expanduser("~/.docker"))
        kube_real = os.path.realpath(os.path.expanduser("~/.kube"))
        assert docker_real in DANGEROUS_PATHS
        assert kube_real in DANGEROUS_PATHS

    def test_windows_paths_on_windows(self) -> None:
        with patch("myrm_agent_harness.core.security.path.filesystem.platform.system", return_value="Windows"):
            from myrm_agent_harness.core.security.path.filesystem import _build_dangerous_paths

            result = _build_dangerous_paths()
            win_paths = {
                "C:\\Windows\\System32",
                "C:\\Windows\\SysWOW64",
                "C:\\Windows",
                "C:\\Program Files",
                "C:\\ProgramData",
            }
            for wp in win_paths:
                real = os.path.realpath(wp)
                assert real in result, f"{wp} should be in dangerous paths on Windows"

class TestIsDangerousPath:
    """Test is_dangerous_path() function."""

    def test_exact_dangerous_path(self) -> None:
        assert is_dangerous_path("/etc") is True

    def test_child_of_dangerous_path(self) -> None:
        assert is_dangerous_path("/etc/passwd") is True
        assert is_dangerous_path("/etc/nginx/nginx.conf") is True

    def test_ssh_dir(self) -> None:
        assert is_dangerous_path("~/.ssh/id_rsa") is True

    def test_docker_dir(self) -> None:
        assert is_dangerous_path("~/.docker/config.json") is True

    def test_kube_dir(self) -> None:
        assert is_dangerous_path("~/.kube/config") is True

    def test_safe_path(self) -> None:
        assert is_dangerous_path("/tmp/safe_file.txt") is False
        assert is_dangerous_path("/home/user/project/main.py") is False

    def test_partial_name_no_false_positive(self) -> None:
        assert is_dangerous_path("/etcetera/something") is False

    def test_tilde_expansion(self) -> None:
        assert is_dangerous_path("~/.aws/credentials") is True

class TestCoversDangerousPath:
    """covers_dangerous_path() refuses a path that equals or contains a dangerous root."""

    @pytest.fixture
    def fake_home(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        home = tmp_path / "home"
        (home / ".ssh").mkdir(parents=True)
        (home / "proj").mkdir()
        monkeypatch.setattr(
            "myrm_agent_harness.core.security.path.filesystem.DANGEROUS_PATHS",
            frozenset({os.path.realpath(home / ".ssh")}),
        )
        return home

    def test_ancestor_of_a_dangerous_root_is_covered(self, fake_home: Path) -> None:
        assert covers_dangerous_path(str(fake_home)) is True
        assert covers_dangerous_path(str(fake_home.parent)) is True

    def test_the_dangerous_root_itself_is_covered(self, fake_home: Path) -> None:
        assert covers_dangerous_path(str(fake_home / ".ssh")) is True

    def test_sibling_project_and_dangerous_descendant_are_not_covered(self, fake_home: Path) -> None:
        assert covers_dangerous_path(str(fake_home / "proj")) is False
        # A path *inside* the root is is_dangerous_path's business, not this predicate's.
        assert covers_dangerous_path(str(fake_home / ".ssh" / "keys")) is False

    def test_symlink_to_an_ancestor_is_resolved(self, fake_home: Path, tmp_path: Path) -> None:
        link = tmp_path / "shortcut"
        link.symlink_to(fake_home, target_is_directory=True)
        assert covers_dangerous_path(str(link)) is True

    def test_partial_name_is_not_an_ancestor(self, fake_home: Path) -> None:
        (fake_home.parent / "home-extra").mkdir()
        assert covers_dangerous_path(str(fake_home.parent / "home-extra")) is False

    def test_empty_and_non_path_text_are_not_covered(self) -> None:
        assert covers_dangerous_path("") is False
        assert covers_dangerous_path("   ") is False
        assert covers_dangerous_path("line one\nline two") is False

    def test_real_roots_filesystem_root_and_home(self) -> None:
        assert covers_dangerous_path("/") is True
        assert covers_dangerous_path("~") is True
        assert covers_dangerous_path("/etc") is True
        assert covers_dangerous_path("/tmp/safe_project") is False


class TestSafeJoinPathAndBoundary:
    """Test safe_join_path and is_within_boundary functions."""

    def test_is_within_boundary_safe(self) -> None:
        from myrm_agent_harness.core.security.path import is_within_boundary

        assert is_within_boundary("/safe/workspace/file.txt", "/safe/workspace") is True
        assert is_within_boundary("/safe/workspace/subdir/file.txt", "/safe/workspace") is True

    def test_is_within_boundary_traversal(self) -> None:
        from myrm_agent_harness.core.security.path import is_within_boundary

        assert is_within_boundary("/safe/workspace/../file.txt", "/safe/workspace") is False
        assert is_within_boundary("/etc/passwd", "/safe/workspace") is False

    def test_safe_join_path_safe(self) -> None:


        result = safe_join_path("/safe/workspace", "subdir/file.txt")
        assert str(result).endswith("subdir/file.txt")

    def test_safe_join_path_null_byte(self) -> None:

        from myrm_agent_harness.core.security.path import safe_join_path

        with pytest.raises(ValueError, match="Null byte injection"):
            safe_join_path("/safe/workspace", "file\0.txt")

    def test_safe_join_path_absolute(self) -> None:

        from myrm_agent_harness.core.security.path import safe_join_path

        with pytest.raises(ValueError, match="Absolute paths are not allowed"):
            safe_join_path("/safe/workspace", "/etc/passwd")

    def test_safe_join_path_traversal(self) -> None:

        from myrm_agent_harness.core.security.path import safe_join_path

        with pytest.raises(ValueError, match="Path traversal detected"):
            safe_join_path("/safe/workspace", "../../etc/passwd")

    def test_safe_join_path_symlink_escape(self, tmp_path) -> None:
        import os

        from myrm_agent_harness.core.security.path import safe_join_path

        # Setup: base_dir and an outside file
        base_dir = tmp_path / "workspace"
        base_dir.mkdir()
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        outside_file = outside_dir / "secret.txt"
        outside_file.write_text("secret")

        # Create a symlink inside workspace pointing outside
        symlink_path = base_dir / "link"
        try:
            os.symlink(outside_file, symlink_path)
        except OSError:
            pytest.skip("Symlinks not supported on this OS/filesystem")

        with pytest.raises(ValueError, match="Path traversal detected"):
            safe_join_path(base_dir, "link")

class TestBlockedDevicePath:
    """Test is_blocked_device_path() and BLOCKED_DEVICE_NAMES."""

    def test_blocked_device_names_set(self) -> None:
        assert "CON" in BLOCKED_DEVICE_NAMES
        assert "NUL" in BLOCKED_DEVICE_NAMES
        assert "PRN" in BLOCKED_DEVICE_NAMES
        assert "AUX" in BLOCKED_DEVICE_NAMES
        assert "COM1" in BLOCKED_DEVICE_NAMES
        assert "LPT1" in BLOCKED_DEVICE_NAMES

    def test_posix_device_paths(self) -> None:
        assert is_blocked_device_path("/dev/zero") is True
        assert is_blocked_device_path("/dev/null") is True
        assert is_blocked_device_path("/dev/urandom") is True
        assert is_blocked_device_path("dev/random") is True
        assert is_blocked_device_path("/proc/kcore") is True
        assert is_blocked_device_path("/sys/kernel") is True

    def test_windows_device_names(self) -> None:
        assert is_blocked_device_path("CON") is True
        assert is_blocked_device_path("con.txt") is True
        assert is_blocked_device_path("NUL") is True
        assert is_blocked_device_path("nul.json") is True
        assert is_blocked_device_path("aux.py") is True
        assert is_blocked_device_path("COM1") is True
        assert is_blocked_device_path(r"\\.\COM1") is True
        assert is_blocked_device_path(r"//./NUL") is True
        assert is_blocked_device_path("src/utils/con.txt") is True

    def test_safe_regular_paths_not_blocked(self) -> None:
        assert is_blocked_device_path("src/index.ts") is False
        assert is_blocked_device_path("config.json") is False
        assert is_blocked_device_path("controller.py") is False
        assert is_blocked_device_path("connect.go") is False
        assert is_blocked_device_path("") is False
        assert is_blocked_device_path("   ") is False
