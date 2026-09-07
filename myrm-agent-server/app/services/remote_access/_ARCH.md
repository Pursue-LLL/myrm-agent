# app/services/remote_access/

## Overview
Remote access host asset management, `~/.ssh/config` parser, and non-blocking parameterized SSH/SFTP client services.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Export remote access models, parser, and SSH execution client services. | ✅ |
| `host_models.py` | Models & Parser | Data structures for `RemoteHostConfig`, `SSHCommandExecutionResult`, `SFTPTransferResult` and OpenSSH config parser. | ✅ |
| `ssh_client_service.py` | Service | Async subprocess-based SSH execution with timeout protection and high-risk command guard. | ✅ |
