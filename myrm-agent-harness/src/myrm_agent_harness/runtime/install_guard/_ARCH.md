# install_guard/

## 概述

安装后验证：确认已安装的 harness wheel 可导入、核心运行时依赖可用、公开 API 可解析，可选校验 Docker 运行镜像的 matplotlib CJK 字体。

归属 `runtime/` 层 — 与 `doctor.py` 并列，回答「这个环境能否跑 Harness / Agent」。

## 文件

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `__init__.py` | 门面 | 模块说明（无 re-export） | ✅ |
| `verify.py` | 核心 | Console script `verify-harness-distribution` 入口；`python -m myrm_agent_harness.runtime.install_guard.verify [--matplotlib-cjk]` | ✅ |

## 依赖

- 父模块 [`../_ARCH.md`](../_ARCH.md)
- `myrm_agent_harness.api`（公开 API 可解析性检查）
