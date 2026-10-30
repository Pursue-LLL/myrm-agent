"""Architecture test: runtime images ship every X11 package the Linux computer-use backend shells out to.

The harness LinuxBackend runs xdotool for input and xclip to paste any text with a non-ASCII character
(xdotool's per-character key remapping drops characters in real applications); an image with xdotool
but no xclip loses all CJK typing. x11-utils provides xprop (the foreground window's WM_CLASS that the
sensitive-app guard keys on) and xdpyinfo (the screen size behind click coordinates); without it the class
name is empty and the size falls back to a guessed 1920x1080.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME_IMAGES = (_SERVER_ROOT / "Dockerfile", _SERVER_ROOT / "docker" / "Dockerfile.official")
_REQUIRED_X11_PACKAGES = ("xdotool", "xclip", "x11-utils")


def _apt_install_block_with(dockerfile: Path, package: str) -> str:
    """The `apt-get install` RUN instruction (continuation lines joined) that installs `package`."""
    joined = dockerfile.read_text().replace("\\\n", " ")
    blocks = [line for line in joined.splitlines() if "apt-get install" in line and re.search(rf"\b{package}\b", line)]
    assert len(blocks) == 1, f"{dockerfile.name}: expected exactly one apt-get install installing {package}"
    return blocks[0]


@pytest.mark.architecture
@pytest.mark.parametrize("dockerfile", _RUNTIME_IMAGES, ids=lambda p: p.name)
@pytest.mark.parametrize("package", _REQUIRED_X11_PACKAGES)
def test_runtime_image_installs_x11_package(dockerfile: Path, package: str) -> None:
    block = _apt_install_block_with(dockerfile, "xdotool")
    assert re.search(rf"\b{package}\b", block), f"{dockerfile.name} must apt-install {package} next to xdotool"
