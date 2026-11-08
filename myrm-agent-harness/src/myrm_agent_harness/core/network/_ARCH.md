# network/

## Overview
IPC socket path and permission policy shared by the MCP transport.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | IPC socket path and permission policy shared by the MCP transport. | — |
| `ipc_socket.py` | Core | IPC socket path and permission policy shared by the MCP transport. — execution_ipc_socket_path: Fresh socket path for one script execution, inside a private per-process directory.; SOCKET_DIR_MODE / SOCKET_FILE_MODE: Owner-only modes for the dir and socket. | ✅ |
