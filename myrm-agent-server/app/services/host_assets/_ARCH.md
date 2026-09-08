# app/services/host_assets/

## Overview
Multi-Host SSH Ops, SFTP Explorer and Agent Host Asset Bridge service suite. Provides secure host credential vaults, ~/.ssh/config parser/importer, and safe SSH & SFTP execution bridges with safety policies.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Host assets package exports. | ✅ |
| `models.py` | Models | Data structures for host configuration, SSH commands, and SFTP file transfers. | ✅ |
| `vault.py` | Storage | In-memory and local storage for host assets + ~/.ssh/config parser. | ✅ |
| `ssh_bridge.py` | Bridge | Safe SSH remote execution bridge with timeout and destructive command interceptor. | ✅ |
| `sftp_bridge.py` | Bridge | Safe SFTP file read/write transfer bridge. | ✅ |
