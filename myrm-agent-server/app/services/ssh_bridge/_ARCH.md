# app/services/ssh_bridge/

## Overview
Multi-host SSH asset vault, connection pooling, SFTP manager, and Agent execution bridge service layer.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Exports core services, vaults, and execution tools. | ✅ |
| `models.py` | Models | Pydantic data schemas for SSH host assets, execution results, and SFTP file metadata. | ✅ |
| `vault.py` | Core Service | Secure encrypted asset vault with local persistence and secret obfuscation. | ✅ |
| `config_importer.py` | Importer | Parser for `~/.ssh/config` importing host blocks into structured `SSHHostAsset` entries. | ✅ |
| `pool.py` | Connection Pool | Async SSH connection manager with keep-alive, handshake probing, and session pooling. | ✅ |
| `sftp_manager.py` | Core Service | SFTP remote directory traversal, file upload/download, and size guards. | ✅ |
| `agent_bridge.py` | Agent Adapter | AI Agent callable interface for controlled remote command dispatch with log distillation. | ✅ |
