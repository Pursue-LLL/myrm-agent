"""Read which CPU a compiled extension module carries machine code for.

[INPUT]
- the leading bytes of a Mach-O (thin or universal), ELF or PE file

[OUTPUT]
- native_binary_machines(): the platform-key machine tokens (``x64`` / ``arm64``) the binary holds code for

[POS]
Evidence behind the core wheel architecture gate (``integrity``). A core wheel is named and stamped for one
platform key, Nuitka cannot cross-compile, and the loader rejects code for another CPU, so the headers are the
only proof the binaries match the key. Pure header parsing: the pre-upload validation job runs on Linux and has
to read Mach-O and PE files too.
"""

from __future__ import annotations

import struct

# PE keeps ``e_lfanew`` in its first 64 bytes and the COFF header right behind it, Mach-O and ELF keep the CPU
# in the first 20: a few KiB is far more than any of them need.
HEADER_BYTES = 4096

_MACHO_CPU = {0x0100000C: "arm64", 0x01000007: "x64"}
_ELF_MACHINE = {183: "arm64", 62: "x64"}
_PE_MACHINE = {0xAA64: "arm64", 0x8664: "x64"}

_MACHO_THIN_64 = b"\xcf\xfa\xed\xfe"
# Universal binaries list one entry per architecture: (cputype, cpusubtype, offset, size, align), 20 bytes in
# the 32-bit table and 32 in the 64-bit table; every field is big-endian. The entry count is untrusted input: the
# loop ends at the end of the header, not at the count.
_FAT_ENTRY_SIZE = {b"\xca\xfe\xba\xbe": 20, b"\xca\xfe\xba\xbf": 32}

_ELF_MAGIC = b"\x7fELF"
_ELF_LITTLE_ENDIAN = 1
_ELF_MACHINE_OFFSET = 18
_PE_POINTER_OFFSET = 0x3C
_PE_SIGNATURE = b"PE\x00\x00"
_MIN_HEADER_BYTES = 64


def _known(table: dict[int, str], code: int) -> frozenset[str]:
    return frozenset({table[code]}) if code in table else frozenset()


def _macho_machines(header: bytes) -> frozenset[str]:
    if header[:4] == _MACHO_THIN_64:
        (cpu,) = struct.unpack_from("<I", header, 4)
        return _known(_MACHO_CPU, cpu)
    entry_size = _FAT_ENTRY_SIZE[header[:4]]
    (count,) = struct.unpack_from(">I", header, 4)
    machines: set[str] = set()
    for index in range(count):
        offset = 8 + index * entry_size
        if offset + 4 > len(header):
            break
        (cpu,) = struct.unpack_from(">I", header, offset)
        machines |= _known(_MACHO_CPU, cpu)
    return frozenset(machines)


def _elf_machines(header: bytes) -> frozenset[str]:
    if header[5] != _ELF_LITTLE_ENDIAN:
        return frozenset()
    (machine,) = struct.unpack_from("<H", header, _ELF_MACHINE_OFFSET)
    return _known(_ELF_MACHINE, machine)


def _pe_machines(header: bytes) -> frozenset[str]:
    (pe_offset,) = struct.unpack_from("<I", header, _PE_POINTER_OFFSET)
    if pe_offset + 6 > len(header) or header[pe_offset : pe_offset + 4] != _PE_SIGNATURE:
        return frozenset()
    (machine,) = struct.unpack_from("<H", header, pe_offset + 4)
    return _known(_PE_MACHINE, machine)


def native_binary_machines(header: bytes) -> frozenset[str]:
    """Machine tokens a native binary holds code for; empty when it is no x64 / arm64 Mach-O, ELF or PE file."""
    if len(header) < _MIN_HEADER_BYTES:
        return frozenset()
    if header[:4] == _MACHO_THIN_64 or header[:4] in _FAT_ENTRY_SIZE:
        return _macho_machines(header)
    if header[:4] == _ELF_MAGIC:
        return _elf_machines(header)
    if header[:2] == b"MZ":
        return _pe_machines(header)
    return frozenset()
