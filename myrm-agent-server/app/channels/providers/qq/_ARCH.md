# qq/

## Overview
QQ channel provider package.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | QQ channel provider package. | — |
| api.py | Core | QQ HTTP layer. Called by channel.py via self._api. | ✅ |
| channel.py | Core | QQ Official Bot channel. WebSocket real-time event reception, REST API message sending, | ✅ |
| helpers.py | Core | Pure helper functions for QQ channel. | ✅ |
