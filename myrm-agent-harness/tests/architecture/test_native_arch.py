"""Architecture gate: the CPU of a compiled module is read from its header, for every platform the release builds."""

from __future__ import annotations

import sys
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
    PE_ARM64,
    PE_X64,
    elf_header,
    fat_macho_header,
    macho_header,
    native_binary_stub,
    pe_header,
)

from harness_packaging.native_arch import native_binary_machines
from harness_packaging.platforms import ALL_PLATFORMS, platform_spec_for_key


@pytest.mark.architecture
@pytest.mark.parametrize(
    ("header", "machine"),
    [
        (macho_header(MACHO_ARM64), "arm64"),
        (macho_header(MACHO_X64), "x64"),
        (elf_header(ELF_ARM64), "arm64"),
        (elf_header(ELF_X64), "x64"),
        (pe_header(PE_ARM64), "arm64"),
        (pe_header(PE_X64), "x64"),
    ],
)
def test_the_header_names_the_cpu_of_each_binary_format(header: bytes, machine: str) -> None:
    assert native_binary_machines(header) == {machine}


@pytest.mark.architecture
def test_a_universal_binary_holds_every_architecture_it_lists() -> None:
    assert native_binary_machines(fat_macho_header(MACHO_X64, MACHO_ARM64)) == {"x64", "arm64"}
    assert native_binary_machines(fat_macho_header(MACHO_ARM64)) == {"arm64"}


@pytest.mark.architecture
def test_a_universal_binary_with_an_absurd_entry_count_is_read_without_running_off_the_header() -> None:
    header = fat_macho_header(MACHO_ARM64)
    forged = header[:4] + (2**31).to_bytes(4, "big") + header[8:]
    assert native_binary_machines(forged) == {"arm64"}


@pytest.mark.architecture
@pytest.mark.parametrize(
    "header",
    [
        b"",
        b"\x7fELF",
        b"MZ" + bytes(62),
        b"not a native binary, just text. " * 4,
        bytes(128),
        elf_header(ELF_X64, data=2),
        elf_header(243),
        macho_header(0x0100000A),
        pe_header(0x01C4),
    ],
    ids=[
        "empty",
        "truncated-elf",
        "pe-without-signature",
        "text",
        "zeros",
        "big-endian-elf",
        "riscv",
        "ppc64",
        "arm32-pe",
    ],
)
def test_anything_that_is_not_an_x64_or_arm64_binary_has_no_machine(header: bytes) -> None:
    assert native_binary_machines(header) == frozenset()


@pytest.mark.architecture
@pytest.mark.parametrize("platform_key", ALL_PLATFORMS)
def test_the_stub_of_every_platform_key_reads_back_as_that_keys_cpu(platform_key: str) -> None:
    assert native_binary_machines(native_binary_stub(platform_key)) == {platform_spec_for_key(platform_key).machine}
