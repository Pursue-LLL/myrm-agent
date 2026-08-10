# hooks/

## 架构概述

React 自定义 Hooks：连接 UI 与 `@/store`、`@/services`、`@/lib`。按业务域子目录组织；**禁止**桶导出（barrel index），`tasks/index.ts` 为唯一允许的桶入口。

## 域划分

| 路径 | 职责 | 文档 |
|------|------|------|
| `message-input/` | 聊天输入、队列、流式渲染、@/Slash、输入历史 | [_ARCH.md](message-input/_ARCH.md) |
| `voice/` | 全双工/PTT 语音（STT/TTS/Realtime/Gemini/Agent bridge） | [_ARCH.md](voice/_ARCH.md) |
| `tauri/` | 桌面 Tauri：invoke、tray、Inline Input/Appshot、更新、电源锁 | [_ARCH.md](tauri/_ARCH.md) |
| `approval/` | 工具审批 HITL、visual snapshot、browser takeover | [_ARCH.md](approval/_ARCH.md) |
| `settings/` | System/Personal/MCP 配置与安全门禁 | [_ARCH.md](settings/_ARCH.md) |
| `billing/` | 订阅、entitlements、配额、ingress | [_ARCH.md](billing/_ARCH.md) |
| `agent/` | 智能体编辑/配置面板/预设/gallery（含 `config-panel/` 子模块） | [_ARCH.md](agent/_ARCH.md) |
| `chat/` | 会话级 UX：`useChatTurnPrewarm`；Tauri composer drop `usePriorChatComposerDrop`（prior_chat cite） | [_ARCH.md](chat/_ARCH.md) |
| `shell/` | 全局 liveness、tab badge、nav badge、快捷键、crash guard | [_ARCH.md](shell/_ARCH.md) |
| `globalEvents/` | SSE 全局事件编排 + toast 子模块（含 `run_digest_updated` → `run-digest-updated`） | [_ARCH.md](globalEvents/_ARCH.md) |
| `copilot/` | Run digest hook（SSE + GET） | [_ARCH.md](copilot/_ARCH.md) |
| `multimodal/` | 摄像头输入、视觉意图（voice/输入 toolbar 共用） | [_ARCH.md](multimodal/_ARCH.md) |
| `pwa/` | PWA 安装、Web Push、What's New | [_ARCH.md](pwa/_ARCH.md) |
| `workspace/` | 工作区流、widget 存储、artifact 版本、batch WS | [_ARCH.md](workspace/_ARCH.md) |
| `ui/` | 通用 UI 行为（scroll、sidebar、drag-drop、media query） | [_ARCH.md](ui/_ARCH.md) |
| `shared/` | 跨域小 hook（toast、draft、diff parser、deploy mode） | [_ARCH.md](shared/_ARCH.md) |
| `tasks/` | 后台任务 WebSocket 订阅 | [_ARCH.md](tasks/_ARCH.md) |

## 根级 Hook

| 文件 | 职责 | I/O/P |
|------|------|-------|
| `useProjectDefaultAgent.ts` | 新建对话时自动注入项目默认智能体的 agentConfig | ✅ |
| `useManagedPolicyEffective.ts` | Org MAP effective 只读状态（mount + CP sync SSE + tab visible / Tauri focus refetch；共享 inflight fetch） | ✅ |
| `useOrgModelPolicySync.ts` | Org model policy visibility / Tauri focus refetch（picker 打开时由 store.loadPolicy 拉取最新 whitelist） | ✅ |
| `useOrgModelPolicy.ts` | Settings 等页面的 org model policy hook（`isModelAllowed` 委托 store SSOT） | ✅ |

## 测试

| 位置 | 说明 |
|------|------|
| `<domain>/__tests__/` | hook 单元测试与实现同域共置（colocated） |
| `__tests__/useManagedPolicyEffective.test.ts` | 根级 MAP hook（mount / visibility refetch / SSE push / revision skip / inflight dedupe / stale YOLO clear） |
| `__tests__/useOrgModelPolicy.test.ts` | 根级 org model policy hook（fail-closed 委托 store / whitelist 匹配） |

政策 SSOT：根 [_ARCH.md](../../_ARCH.md)「测试」表（默认 colocated）。

## 依赖

- `@/store/*` — Zustand 状态
- `@/services/*` — REST/SSE 客户端
- `@/lib/*` — 纯函数与常量

## 约束

- Hook 内不写 UI JSX（除 `globalEvents/*.tsx` 等 toast 渲染例外）。
- 单文件 >400 行应拆分子 hook 或下沉逻辑到 `@/lib`；**已在** `scripts/ci/file_line_budget_baseline.txt` **登记者为 CI 存量豁免**（禁止新增超标文件，见 `scripts/check_file_line_budget.py`）。
- 域外 import：`@/hooks/<domain>/<file>`；域内优先相对 import。
- 桶导出政策见根 [_ARCH.md](../../_ARCH.md)「桶导出政策」表。
