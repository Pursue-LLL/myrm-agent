# execution/

## Overview
Coordinate-based fallback execution for an action the native AX route cannot perform on a @dref element. A native failure that is stale or of unknown outcome never reaches it.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Coordinate-based fallback execution package | — |
| healer.py | Core | BBox center click/type fallback via ComputerBackend (a text action clicks the element before it types); macOS routes to snapshot pid with foreground guard | ✅ |

## Dependencies

- `computer_use/dref/types.py` (POS: ElementRef with BBox)
- `types.py` (POS: ActionResult, ModifierKey)
- Used by `desktop_session/interact.py::desktop_interact` (POS: semantic desktop orchestrator)

## Architecture Overview

Detailed design: [DESKTOP_SYSTEM.md](../DESKTOP_SYSTEM.md)
