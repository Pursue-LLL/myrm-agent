# adaptive_wakeup/

## Overview
Adaptive Wakeup Driver package for bounded autonomous settlements.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Adaptive Wakeup Driver package for bounded autonomous settlements. | — |
| `adaptive_router.py` | Core | Adaptive wakeup router deciding between followup, degradation, or suppression. `route` only reads the budget and the user's stop flag, so settlements that share one wake turn cost one wake; the host spends it with `claim_wake_turn` when the turn actually starts. | ✅ |
| `budget_tracker.py` | Core | Thread-safe session-scoped wakeup budget tracker. | ✅ |
| `types.py` | Types | Strongly-typed DTOs and Enums for Adaptive Wakeup Driver. | ✅ |
