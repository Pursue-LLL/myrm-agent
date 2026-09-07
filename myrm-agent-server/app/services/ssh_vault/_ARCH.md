# app/services/ssh_vault/

## Overview
SSH Asset Vault and Host Configuration Discovery Service.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | SSH asset vault package exports. | ✅ |
| `models.py` | Models | Data structures for SSH hosts, probing, and commands (`SSHHostConfig`, `SSHProbeResult`, `SSHAssetSummary`). | ✅ |
| `service.py` | Service | SSH config parser and network reachability probing (`SSHAssetService`). | ✅ |
