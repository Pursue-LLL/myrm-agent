# tests/architecture/ 模块架构

## 架构概述

Server 层架构约束测试：禁止新增 harness 深导入、禁止 `uv.lock` editable harness pin。

## 文件清单

| 文件 | 职责 |
|------|------|
| `test_server_harness_imports.py` | 相对 baseline 禁止新增 server→harness 内部 import |
| `test_uv_lock_harness_registry.py` | `uv.lock` 必须 PyPI registry pin，禁止 editable |
| `test_no_user_id.py` | 单机 server 禁止多租户 user_id 泄漏 |
| `data/server_harness_import_baseline.txt` | harness import 允许 baseline |

## 依赖

- `myrm-agent-server/pyproject.toml` — harness 版本 pin
- `myrm-agent-server/uv.lock` — lock 源必须为 PyPI
