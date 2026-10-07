# scripts/dev 模块架构

## 架构概述

`myrm-agent-server` 本地开发与 CI 辅助脚本。与仓根 [scripts/dev/_ARCH.md](../../../scripts/dev/_ARCH.md)（栈启动 / MCP Chrome E2E 胶水）职责分离：本目录服务 server pytest、内存 profiling 与历史数据一次性回填。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `profile_test_memory.py` | 工具 | 按 test 文件测量 peak RSS（macOS `time -l`） | ✅ |
| `run_tests_low_memory.sh` | 工具 | 本地低内存 pytest（`-n0`；`PYTEST_XDIST_WORKERS=N`）；**非** live E2E 联调 | ✅ |
| `backfill-chat-usage.py` | 工具 | 按消息 `extra_data` 重算 `Chat.total_calls/total_tokens/total_usd`（默认仅改写陈旧值，`--force` 全量重写）；历史数据一次性回填，复用 `app.api.statistics.usage_aggregation` 与 `ChatRepository` | — |

## 依赖

- [scripts/_ARCH.md](../_ARCH.md) — 父目录 deploy CLI 与 CI 门禁
- [scripts/ci/run_default_tests.sh](../ci/run_default_tests.sh) — 默认 pytest 入口

## 约束

- 可重复的 API/契约验证放在 `tests/`；禁止在此新增「半 pytest」一次性联调脚本（纪律见仓根 [scripts/dev/_ARCH.md](../../../scripts/dev/_ARCH.md)）
