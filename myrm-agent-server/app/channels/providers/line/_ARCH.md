# line/

## Overview
LINE channel provider via Messaging API.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | LINE channel provider via Messaging API. | — |
| api.py | Core | LINE HTTP layer. Called by channel.py via self._api. | ✅ |
| channel.py | Core | LINE integration: webhook inbound, Reply/Push outbound, mention detection, quote-token context linki | ✅ |
| helpers.py | Core | LINE webhook type definitions and constants. Referenced by channel.py. | ✅ |
