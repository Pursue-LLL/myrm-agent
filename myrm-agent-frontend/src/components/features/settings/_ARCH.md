# settings 模块架构

## 架构概述

设置页壳层：`SettingsLayout`（URL 为唯一数据源 + Section 缓存）、`SettingsMenu`（分组导航）、共享表单 primitive。各业务 Section 在 `sections/` 按 `SettingsMenu` 六组组织。

## 核心文件

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `SettingsLayout.tsx` | 核心 | Tab 路由、动态加载 Section、脏状态守卫 | ✅ |
| `SettingsMenu.tsx` | 核心 | 分组侧栏（personal / ai-core / ai-tools / knowledge / integration / system） | ✅ |
| `SettingsIcons.tsx` | 辅助 | 设置页图标映射 | ✅ |
| `FormFields.tsx` | 辅助 | 通用表单字段 | ✅ |
| `SchemaForm.tsx` | 辅助 | JSON Schema 驱动表单 | ✅ |
| `ConfigImportExport.tsx` | 辅助 | 配置导入导出 | ✅ |
| `MCPConfigForm.tsx` | 辅助 | MCP 顶层表单（详情见 `mcp/`） | ✅ |

## 子目录

| 目录 | 职责 | 文档 |
|------|------|------|
| `sections/` | 各设置 Tab 的 Section 组件（六组子目录） | [sections/_ARCH.md](sections/_ARCH.md) |
| `sections/integration/` | 集成域 Section（扩展桥、凭证、外部 Agent、通信容器） | [sections/integration/_ARCH.md](sections/integration/_ARCH.md) |
| `sections/integration/channels/` | 渠道、路由、语音配置卡片 | [sections/integration/channels/_ARCH.md](sections/integration/channels/_ARCH.md) |
| `sections/knowledge/wiki/` | Wiki 设置 | [sections/knowledge/wiki/_ARCH.md](sections/knowledge/wiki/_ARCH.md) |
| `mcp/` | MCP 列表/编辑/安全扫描 Ack | [mcp/_ARCH.md](mcp/_ARCH.md) |
| `common/` | 骨架屏、共享 UI | 模块内文件 |
| `default-model/` | 默认模型子表单 | 模块内文件 |
| `model-service/` | 模型服务配置 | 模块内文件 |
| `retrieval/` | 检索服务配置 | 模块内文件 |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
