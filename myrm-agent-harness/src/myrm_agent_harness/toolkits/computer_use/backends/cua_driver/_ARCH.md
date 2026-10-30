# backends/cua_driver/

## Overview
Background-input backend that proxies input actions to cua-driver over MCP stdio and delegates everything else to the native backend.

Optional enhancement. Wraps the platform-native backend; never imported when cua-driver is not installed.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | cua-driver 后台输入后端包入口（无再导出，调用方按子模块导入）。 | — |
| backend.py | Enhancement | Background-input backend via cua-driver MCP. Wraps a native backend. | ✅ |
| spawn.py | Enhancement | MCP stdio argv policy — ``--no-overlay`` defaults and ``--help`` capability probe. | ✅ |
