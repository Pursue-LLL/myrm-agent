# app/services/remote_host/

## Overview
Remote SSH Host Asset Management models and discovery service.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Remote host package exports. | ✅ |
| `manager.py` | Service | RemoteHostManager for host CRUD and ~/.ssh/config parser. | ✅ |
| `models.py` | Models | Data structures for remote hosts (`RemoteHostConfig`, `RemoteHostSummary`, `HostAssetImportResult`). | ✅ |
