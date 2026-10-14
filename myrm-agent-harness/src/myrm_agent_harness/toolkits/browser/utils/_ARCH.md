# utils/

## Overview
Shared utilities and constants for the browser toolkit.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Exports utility components. | ✅ |
| selectors.py | Core | Shared CSS selectors (e.g., PASSWORD_FIELD_SELECTOR). | ✅ |
| proxy_error.py | Core | Proxy and network error pattern detection for browser navigation diagnostics | ✅ |
| timeout.py | Core | Timeout detection helper: `timeout_error_types()` (cached builtin + patchright `TimeoutError` tuple for `except` clauses, patchright imported on first call) and `is_timeout_error`; the two classes do not share a base class. | ✅ |
