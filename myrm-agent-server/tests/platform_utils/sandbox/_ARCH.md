# tests/platform_utils/sandbox 模块架构

---

## 架构概述

`app/platform_utils/sandbox`（平台适配层沙箱子模块）的业务逻辑回归测试。覆盖 SaaS 沙箱启动时平台 provider seed 全分支（全新沙箱写入、已有配置跳过、守卫子句）与沙箱 tool gateway 凭据合并。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `test_saas_providers_seed.py` | 核心 | `seed_saas_platform_providers_if_needed` 全分支（14 例）：全新沙箱 seed / providers 空数组 seed / record.value 非 dict 防御 seed / 有 provider 跳过（含未设默认模型回归保护）/ 仅默认模型跳过 / 非 sandbox 返回 / 缺 env 返回（WARNING 锚点）/ 非法 ref 返回 / `_parse_lite_model_ref` 4 例 |
| `test_saas_providers_seed_integration.py` | 核心 | seed 集成（2 例）：真实 `ConfigService` + 内存 SQLite 全链路——platform provider 加密落库并读回、已有用户 provider 不被覆盖。关键路径（真实 ConfigService 读写）不 mock，仅隔离 session factory |
| `test_tool_gateway.py` | 核心 | 沙箱 tool gateway 凭据 fetch + merge 单测（非 sandbox 透传、sandbox 平台覆盖、SSRF/格式守卫） |

---

## 依赖关系

- `app.platform_utils.sandbox.saas_providers_seed`
- `app.config.deploy_mode`（`DEPLOY_MODE` lru_cache 控制）
- `app.services.config.service::ConfigService`（单测以替身注入；集成测试用真实实现 + 内存 SQLite）

---

## 运行

```bash
.venv/bin/pytest tests/platform_utils/sandbox/ -q
```
