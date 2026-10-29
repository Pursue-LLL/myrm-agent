# api/companion/

## 架构概述

Companion 伴随模式 HTTP 层：Observer 反应、Evolution 指标、Companion 配置，以及 `pets/` 子包里的 Petdex 安装/list/serve/uninstall。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `router.py` | 路由 | Companion API 端点与 `companion_mode` feature gate。Observer 反应（`load_llm_from_model_config` wire-aware）、Evolution 指标、Companion 配置（含旧精灵配置迁移）；挂载 `pets/` 的宠物端点。 | ✅ |
| `doctor_router.py` | 路由 | `GET /companion/doctor` 无 feature gate 只读诊断 | ✅ |
| `pets/` | 子包 | Petdex 宠物的安装 / 列表 / 精灵图 / 卸载端点与伴侣配置里的精灵选择，见 [pets/_ARCH.md](pets/_ARCH.md) | — |
