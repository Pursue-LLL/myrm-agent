# self_evolution/

## 架构概述

“设计师之眼”自进化流水线与灾备恢复后端 API：接收前端元素圈选上下文（CSS 选择器、标签、类名、组件提示、React Fiber 层级、源码行号、用户诉求及计算样式），提供源码组件 AST 反查与候选推荐（`POST /locate`），自动生成 UI 自进化改造工单、目标文件解析及安全回滚快照点；支持一键 `/recover` 安全还原至最近稳定版本。

## 文件清单

| 文件 | 职责 |
| ---- | ---- |
| `__init__.py` | 包门面：导出 `router` |
| `routes.py` | 源码定位搜索（`POST /locate`）、自进化任务提交（`POST /tasks`）、历史查询（`GET /tasks`）与安全回滚（`POST /recover`）端点 |
| `_ARCH.md` | 本文档：模块架构与契约规范 |

## 依赖

- FastAPI / Pydantic v2
- 内存级沙箱作用域状态持久化

## 用户入口

- 前端 `DesignerEyeOverlay` 元素圈选提交
- 前端 `domSourceLocator` 逆向定位与 AST 候选匹配
- 快捷指令 `/recover` 安全恢复
