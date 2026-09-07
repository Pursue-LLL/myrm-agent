# Host Assets Domain Architecture

## Directory Index
| File | Role | Description |
|------|------|-------------|
| `models.py` | Core | Data models for remote host assets, credentials, and configurations |
| `vault.py` | Service | Encrypted vault storage for host assets and credentials |
| `ssh_bridge.py` | Service | SSH connection and command execution bridge |

## Boundary
Domain service layer under `app/services/host_assets/`.
