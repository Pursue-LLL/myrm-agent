"""Network-share and NT-namespace spellings are refused on their text alone, and Windows reserved names are complete.

On Windows, opening ``\\\\host\\share\\x`` makes the operating system connect to ``host`` and authenticate, which
lets a path that a prompt injection names collect the user's credentials. The decision therefore has to be taken from
the text, before the first ``stat`` or ``resolve``. Every case here is a string: it runs on any host, with the host
flag set by the test, and the real-Windows run (CI) repeats it with the native flag.
"""

from __future__ import annotations

import os

import pytest

from myrm_agent_harness.core.security.path import filesystem as filesystem_module
from myrm_agent_harness.core.security.path.filesystem import (
    BLOCKED_DEVICE_NAMES,
    is_blocked_device_path,
    is_network_or_nt_path,
    network_path_refusal,
)
from tests.support.network_path_probe import (
    ORDINARY_PATHS,
    REFUSED_ON_EVERY_HOST,
    REFUSED_ON_WINDOWS_ONLY,
    forbid_touching,
)


@pytest.fixture(params=[True, False], ids=["windows-host", "posix-host"])
def host_is_windows(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> bool:
    monkeypatch.setattr(filesystem_module, "_IS_WINDOWS", request.param)
    return bool(request.param)


class TestNetworkAndNtSpellings:
    @pytest.mark.parametrize("spelling", REFUSED_ON_EVERY_HOST.values(), ids=REFUSED_ON_EVERY_HOST.keys())
    def test_windows_syntax_is_refused_on_every_host(self, spelling: str, host_is_windows: bool) -> None:
        assert is_network_or_nt_path(spelling) is True

    @pytest.mark.parametrize("spelling", REFUSED_ON_WINDOWS_ONLY.values(), ids=REFUSED_ON_WINDOWS_ONLY.keys())
    def test_forward_slash_unc_is_refused_only_on_a_windows_host(self, spelling: str, host_is_windows: bool) -> None:
        assert is_network_or_nt_path(spelling) is host_is_windows

    @pytest.mark.parametrize("path", ORDINARY_PATHS)
    def test_ordinary_paths_pass_on_every_host(self, path: str, host_is_windows: bool) -> None:
        assert is_network_or_nt_path(path) is False

    @pytest.mark.parametrize("spelling", REFUSED_ON_EVERY_HOST.values(), ids=REFUSED_ON_EVERY_HOST.keys())
    def test_the_shared_device_check_refuses_them_before_the_filesystem(
        self, spelling: str, host_is_windows: bool, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        touches = forbid_touching(monkeypatch)
        assert is_blocked_device_path(spelling) is True
        assert touches == []

    @pytest.mark.parametrize("spelling", REFUSED_ON_WINDOWS_ONLY.values(), ids=REFUSED_ON_WINDOWS_ONLY.keys())
    def test_the_shared_device_check_refuses_forward_slash_unc_on_a_windows_host(
        self, spelling: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(filesystem_module, "_IS_WINDOWS", True)
        touches = forbid_touching(monkeypatch)
        assert is_blocked_device_path(spelling) is True
        assert touches == []

    @pytest.mark.skipif(os.name != "nt", reason="needs the native Windows rules")
    def test_a_windows_host_refuses_the_forward_slash_unc_natively(self) -> None:
        for spelling in REFUSED_ON_WINDOWS_ONLY.values():
            assert is_network_or_nt_path(spelling) is True
            assert is_blocked_device_path(spelling) is True

    def test_the_refusal_names_the_path_and_the_way_out(self) -> None:
        text = network_path_refusal(r"\\evil.test\share\a.txt")
        assert r"\\evil.test\share\a.txt" in text
        assert "mapped drive letter" in text


class TestWindowsReservedNames:
    @pytest.fixture(autouse=True)
    def _windows_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(filesystem_module, "_IS_WINDOWS", True)

    @pytest.mark.parametrize(
        "path",
        [
            "NUL.txt",
            "nul",
            "dir/aux.md",
            "a/CON",
            "com1",
            "Lpt9.TXT",
            r"dir\PRN.txt",
            "NUL .txt",
            "NUL   .txt",
            "a/NUL /b",
            "CONIN$",
            "CONOUT$.log",
            "COM\u00b9",
            "COM\u00b2.log",
            "COM\u00b3",
            "LPT\u00b9",
            "LPT\u00b2.txt",
            "LPT\u00b3",
            "CON:",
            "nul:stream",
            "com1:",
            "dir/aux.md:5-9",
            r"C:\proj\PRN:x",
        ],
    )
    def test_reserved_name_is_blocked(self, path: str) -> None:
        assert is_blocked_device_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "COM10.txt",
            "CONIN.txt",
            "console.txt",
            "auxiliary/readme.md",
            "src/nullable.py",
            "nul-file.txt",
            "my.nul",
            "controller.py",
            "C:/proj/notes.txt",
            r"D:\proj\con_test.py",
            "notes:v2.md",
            "docs/null:stream.md",
        ],
    )
    def test_lookalike_is_not_blocked(self, path: str) -> None:
        assert is_blocked_device_path(path) is False

    def test_the_name_set_holds_the_console_and_superscript_devices(self) -> None:
        assert {"CONIN$", "CONOUT$", "COM\u00b9", "COM\u00b2", "COM\u00b3", "LPT\u00b9", "LPT\u00b2", "LPT\u00b3"} <= (
            BLOCKED_DEVICE_NAMES
        )
        assert {"CONIN", "CONOUT"}.isdisjoint(BLOCKED_DEVICE_NAMES)

    @pytest.mark.skipif(os.name == "nt", reason="a real Windows host resolves these names to devices")
    def test_the_names_are_ordinary_files_on_a_posix_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(filesystem_module, "_IS_WINDOWS", False)
        for path in ("NUL.txt", "NUL .txt", "CONIN$", "COM\u00b9", "dir/aux.md"):
            assert is_blocked_device_path(path) is False
