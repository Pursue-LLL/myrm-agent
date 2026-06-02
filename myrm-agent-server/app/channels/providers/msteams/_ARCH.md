# msteams/

## Overview
Toolkits Channels Providers Msteams module.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package |   Init   | — |
| api.py | Core | Bot Framework HTTP layer. Wraps OAuth token management, serviceUrl caching, | ✅ |
| channel.py | Core | MSTeams Bot channel implementation. Supports message edit/delete, Adaptive Card interactive | ✅ |
| helpers.py | Core | Stateless helpers extracted from MSTeamsChannel to keep channel.py focused | ✅ |
| models.py | Core | Pydantic models for Microsoft Bot Framework activity payloads. | ✅ |
