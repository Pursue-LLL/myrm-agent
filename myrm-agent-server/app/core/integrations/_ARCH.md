# core/integrations/

## 架构概述

外部服务集成的核心领域模型。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 模块入口 | ✅ |
| `catalog/` | 子模块 | Integration Catalog 预配置服务目录（模型、注册表、JSON 数据），详见 [catalog/_ARCH.md](catalog/_ARCH.md) | ✅ |
