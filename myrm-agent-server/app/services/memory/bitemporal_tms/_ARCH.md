# Bitemporal TMS Service Module

## Overview
Adapter service bridging FastAPI controllers with the core bitemporal truth maintenance engine.
Translates Pydantic V2 DTOs and domain entities with strictly-typed contracts.

## Architectural Responsibilities
- `provider.py`: Implements `BitemporalTmsProvider`, converting incoming requests to harness domain operations and serializing responses.
- `__init__.py`: Provides package exports and dependency injection factory `get_bitemporal_tms_provider`.

## File Manifest
| File | Responsibility |
| :--- | :--- |
| `provider.py` | Bitemporal TMS service provider implementation |
| `__init__.py` | Package exports and singleton factory |
