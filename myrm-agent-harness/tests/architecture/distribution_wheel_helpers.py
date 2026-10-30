"""Shared wheel zip fixtures for distribution artifact architecture tests."""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path

from harness_packaging.integrity import manifest_compiled_artifact_prefix
from harness_packaging.platforms import platform_spec_for_key
from harness_packaging.release import manifest_source_paths

MACHO_ARM64, MACHO_X64 = 0x0100000C, 0x01000007
ELF_ARM64, ELF_X64 = 183, 62
PE_ARM64, PE_X64 = 0xAA64, 0x8664

# Real headers are followed by the rest of the file; the padding keeps the stubs above the parser's minimum size.
_HEADER_PADDING = bytes(64)
_PE_OFFSET = 0x40


def macho_header(cpu: int) -> bytes:
    """Thin 64-bit Mach-O header for a Mach-O ``cputype``."""
    return b"\xcf\xfa\xed\xfe" + struct.pack("<I", cpu) + _HEADER_PADDING


def fat_macho_header(*cpus: int) -> bytes:
    """Universal Mach-O header listing one 32-bit fat entry per ``cputype``."""
    entries = b"".join(struct.pack(">IIIII", cpu, 0, 4096, 1, 12) for cpu in cpus)
    return b"\xca\xfe\xba\xbe" + struct.pack(">I", len(cpus)) + entries + _HEADER_PADDING


def elf_header(machine: int, *, data: int = 1) -> bytes:
    """64-bit ELF header for an ``e_machine`` (``data`` 1 = little-endian, 2 = big-endian)."""
    ident = b"\x7fELF" + bytes([2, data, 1]) + bytes(9)
    return ident + struct.pack("<HH", 3, machine) + _HEADER_PADDING


def pe_header(machine: int) -> bytes:
    """PE header: a DOS stub whose pointer at 0x3C leads to the ``PE`` signature and COFF ``Machine``."""
    dos_stub = b"MZ" + bytes(58) + struct.pack("<I", _PE_OFFSET)
    return dos_stub + b"PE\x00\x00" + struct.pack("<H", machine) + _HEADER_PADDING


_STUB_HEADERS = {
    ("darwin", "arm64"): macho_header(MACHO_ARM64),
    ("darwin", "x64"): macho_header(MACHO_X64),
    ("linux", "arm64"): elf_header(ELF_ARM64),
    ("linux", "x64"): elf_header(ELF_X64),
    ("win32", "arm64"): pe_header(PE_ARM64),
    ("win32", "x64"): pe_header(PE_X64),
}


def native_binary_stub(platform_key: str) -> bytes:
    """Smallest binary the core wheel gate accepts for ``platform_key``: the native header of its OS and CPU."""
    return _STUB_HEADERS[platform_key.split("-", 1)[0], platform_spec_for_key(platform_key).machine]


def stub_compiled_artifact_path(manifest_py: str, *, tag: str = "cpython-313-test") -> str:
    """Return a wheel entry path that satisfies core-wheel compiled artifact rules."""
    return f"{manifest_compiled_artifact_prefix(manifest_py)}{tag}.so"


def write_minimal_release_wheel(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("myrm_agent_harness/api/__init__.py", "# public")


def write_minimal_core_wheel(path: Path, platform_key: str = "linux-x64", *, binary: bytes | None = None) -> None:
    """Core wheel stamped ``platform_key`` whose compiled modules are ``binary`` (default: native to the key)."""
    stub = native_binary_stub(platform_key) if binary is None else binary
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "myrm_agent_harness_core/__init__.py",
            (
                '__version__ = "0.1.0"\n'
                f'__platform_key__: str = "{platform_key}"\n'
                "def get_platform_key() -> str:\n"
                "    return __platform_key__\n"
            ),
        )
        for manifest_py in manifest_source_paths():
            zf.writestr(stub_compiled_artifact_path(manifest_py), stub)
