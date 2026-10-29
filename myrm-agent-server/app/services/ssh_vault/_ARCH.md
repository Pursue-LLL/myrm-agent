# app/services/ssh_vault/

## Overview
SSH Asset Vault, Host Configuration Discovery, and Protected Change Window Security Gate Service.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | SSH asset vault package exports. | ✅ |
| `models.py` | Models | Data structures for SSH hosts, probing, and commands (`SSHHostConfig`, `SSHProbeResult`, `SSHAssetSummary`). | ✅ |
| `change_window.py` | Security Gate | Protected change window and single-use break-glass token authorization service (`ProtectedChangeWindowService`); the log line of a consumed token shows the command masked and cut (`command_preview`). | ✅ |
| `service.py` | Service | SSH config parser, network reachability probing, and safe subprocess execution with read-only gates (`SSHAssetService`); the log line of a blocked command shows it masked and cut (`command_preview`). | ✅ |
