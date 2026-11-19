# strategies/

## Overview
File system strategy module.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | File system strategy module. | — |
| base.py | Core | Provides FileSystemStrategy. | ✅ |
| mcp_strategy.py | Core | Provides MCPFileSystemStrategy. | ✅ |
| storage_strategy.py | Core | StorageBackendStrategy: read, write, list, existence and size over a StorageProvider. | ✅ |
| strategy_factory.py | Core | Provides FileSystemStrategyFactory. | ✅ |

## Key Dependencies

- `backends`
- `toolkits`
- `utils`
