# toolchains/

## Overview
Isolated portable toolchain manager for external CLI agents (Node.js download, npm CLI install) without polluting the host OS environment.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports TOOLCHAIN_BASE_DIR and IsolatedToolchainManager | — |
| manager.py | Core | IsolatedToolchainManager — download the portable Node (`NODE_VERSION`, a line that reads `NODE_USE_SYSTEM_CA`), install/resolve CLI binaries under `~/.myrm-agent/toolchains`; the npm child gets `NODE_USE_SYSTEM_CA=1` through `infra/tls_compat.py::with_node_system_ca` while enterprise network compatibility is on, so the install trusts the operating system's store behind a TLS-inspection proxy. The managed Node only runs the install; a delegated CLI runs on the host's `node` | ✅ |

## Module Dependencies

- Pure stdlib + asyncio; used by `toolkits/acp/` runtime backends

## Division vs toolkits/acp/

| Package | Responsibility |
|---------|----------------|
| `toolkits/acp/` | ACP protocol server, runtime, permission, event bus |
| `toolchains/` | Isolated Node/npm environment for CLI-based ACP backends |
