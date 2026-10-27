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
| bwrap.py | Core | Linux bubblewrap (bwrap) sandbox provider. `read_only_subpaths` become `--ro-bind` overlays placed after the writable binds (a later mount covers an earlier one; a mount point cannot be renamed or removed). The directories above each one (`movable_ancestors`) are bound onto themselves first, outer to inner, so they are mount points too and cannot be renamed away and replaced. | ✅ |
| null.py | Core | No-op sandbox provider — transparent passthrough. | ✅ |
| seatbelt.py | Core | macOS sandbox-exec (Seatbelt) sandbox provider. Every path is written into the profile through `_sbpl_string` (backslash and double quote escaped), so a workspace path cannot close the literal and append rules. `read_only_subpaths` become `deny file-write*` rules after the writable allows (a later rule wins), plus a `literal` deny on every directory above a protected path that lies inside a writable area (`movable_ancestors`, the scratch `/tmp` counts as one), so none of them can be renamed away, edited under another name and renamed back, or replaced by a pointer file. | ✅ |
