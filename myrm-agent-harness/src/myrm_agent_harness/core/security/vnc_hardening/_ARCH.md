# vnc_hardening/

## Overview

VNC hardening suite for the native x11vnc server: launch arguments are rebuilt so the server binds to loopback (`-localhost`) by default, never runs with `-nopw`, and always authenticates through an rfbauth password file; a non-loopback bind needs an explicit opt-in plus a separate strong password. A raw argument list can also be audited without being rebuilt.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Package facade: the single import point for the facade, the sanitizer, the password manager and the domain types. | ✅ |
| `config_sanitizer.py` | Core | Rebuilds the x11vnc argument list: requires an rfbauth password file, strips `-nopw`, binds to loopback unless a non-loopback opt-in with a strong dedicated password is given, and checks the password file permissions. | ✅ |
| `facade.py` | Core | Entry point: builds a hardened launch spec, audits a raw argument list for `-nopw`, a missing `-rfbauth` and a missing `-localhost`, and exposes password generation and strength checks. | ✅ |
| `passwd_manager.py` | Core | Judges password strength (at least 8 characters with a letter and a digit), generates random passwords and tightens the rfbauth file to owner-only 0600. | ✅ |
| `types.py` | Types | Bind-mode, auth-policy and violation enums plus the launch-config, hardened-spec, violation and report models. | ✅ |
