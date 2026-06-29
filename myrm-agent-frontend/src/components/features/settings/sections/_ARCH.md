# settings/sections 模块架构

## 架构概述

设置页各 Tab 对应的 Section 组件，目录结构与 `SettingsMenu.tsx` 六组导航对齐。共享 primitive（`SettingsSection.tsx`）保留在本目录根级。

## 域划分（与 SettingsMenu 同构）

| 子目录 | 对应菜单组 | 职责 |
|--------|------------|------|
| `personal/` | personal | 账户、偏好、个性化 |
| `ai-core/` | ai-core | 模型、搜索、Agent（含 `agent/` 子组件） |
| `ai-tools/` | ai-tools | MCP、技能、工具质量 |
| `knowledge/` | knowledge | 记忆、Wiki（含 `wiki/`）、迁移向导 |
| `integration/` | integration | 凭证、外部 Agent、浏览器扩展桥、渠道（含 `channels/`、`integrations/`） |
| `system/` | system | 安全、健康、开发者、关于（见 [system/_ARCH.md](system/_ARCH.md)） |

## 相对 import 铁律

| 文件位置 | 目标 | import |
|----------|------|--------|
| `sections/{group}/X.tsx` | `sections/SettingsSection` | `../SettingsSection` |
| `sections/{group}/X.tsx` | `settings/common` 等壳层 sibling | `../../common/...` |
| `sections/{group}/X.tsx` | `sections/{other}/Y` | `../{other}/Y` |
| `sections/{group}/{sub}/X.tsx` | `sections/SettingsSection` | `../../SettingsSection` |
| `sections/{group}/{sub}/X.tsx` | `settings/common` 等 | `../../../common/...` |
| `sections/knowledge/X.tsx` | `features/checkpoint` | `../../../checkpoint/...` |
| `sections/system/X.tsx` | `features/health` | `../../../health/...` |

## 根级共享文件

| 文件 | 职责 |
|------|------|
| `SettingsSection.tsx` | Section 标题/描述/内容容器 |

## 容器 Section

| 文件 | 职责 |
|------|------|
| `integration/CommunicationSection.tsx` | 渠道 Tab 容器 |
| `ai-core/ModelSettingsSection.tsx` | 模型 Tab 容器 |
| `knowledge/MemoryCenterSection.tsx` | 记忆 Tab 容器 |
| `system/DeveloperCenterSection.tsx` | 开发者 Tab 容器 |
| `system/SystemCenterSection.tsx` | 系统 Tab 容器 |

## 子目录文档

| 路径 | 文档 |
|------|------|
| `ai-core/agent/` | [ai-core/agent/_ARCH.md](ai-core/agent/_ARCH.md) |
| `integration/` | [integration/_ARCH.md](integration/_ARCH.md) |
| `integration/channels/` | [integration/channels/_ARCH.md](integration/channels/_ARCH.md) |
| `integration/integrations/` | [integration/integrations/_ARCH.md](integration/integrations/_ARCH.md) |
| `personal/` | [personal/_ARCH.md](personal/_ARCH.md) |
| `ai-core/` | [ai-core/_ARCH.md](ai-core/_ARCH.md) |
| `ai-tools/` | [ai-tools/_ARCH.md](ai-tools/_ARCH.md) |
| `system/` | [system/_ARCH.md](system/_ARCH.md) |
| `knowledge/wiki/` | [knowledge/wiki/_ARCH.md](knowledge/wiki/_ARCH.md) |
| `knowledge/` | [knowledge/_ARCH.md](knowledge/_ARCH.md) |

## 依赖

- [settings/_ARCH.md](../_ARCH.md)
- `@/services/*`、`@/store/*`
