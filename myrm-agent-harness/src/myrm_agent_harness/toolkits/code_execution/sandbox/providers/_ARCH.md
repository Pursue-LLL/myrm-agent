# providers/

## Overview
Built-in sandbox providers. Each platform has a dedicated provider:

| Platform | Provider | Mechanism |
|----------|----------|-----------|
| Linux | BwrapProvider | bubblewrap namespace isolation |
| macOS | SeatbeltProvider | sandbox-exec SBPL profile |
| Windows | AppContainerProvider | AppContainer security token |
| Fallback | NullProvider | transparent passthrough (no isolation) |

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Built-in sandbox providers. | — |
| _win32_defs.py | Internal | Win32 ctypes structures and low-level API helpers. | ✅ |
| appcontainer.py | Core | Windows AppContainer native process sandbox. Grants ACLs for `writable_paths` and `readable_paths` only: `SandboxPolicy.read_only_subpaths` is **not enforced** here. | ✅ |
| bwrap.py | Core | Linux bubblewrap (bwrap) sandbox provider. `read_only_subpaths` become `--ro-bind` overlays placed after the writable binds (a later mount covers an earlier one; a mount point cannot be renamed or removed). | ✅ |
| null.py | Core | No-op sandbox provider — transparent passthrough. | ✅ |
| seatbelt.py | Core | macOS sandbox-exec (Seatbelt) sandbox provider. Every path is written into the profile through `_sbpl_string` (backslash and double quote escaped), so a workspace path cannot close the literal and append rules. `read_only_subpaths` become `deny file-write*` rules after the writable allows (a later rule wins), plus a `literal` deny on the entry that holds each protected path so it cannot be renamed away or replaced by a pointer file. | ✅ |
