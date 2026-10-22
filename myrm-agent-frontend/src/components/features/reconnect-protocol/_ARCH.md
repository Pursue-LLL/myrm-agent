# reconnect-protocol/

## 架构概述

基于单次原子状态快照与零事件重放 Live SSE 订阅的前后端无缝重连协议前端模块（Item 36 P0）。
直击长任务弱网重连与移动端重连核心痛点，彻底解决重连回放大量历史事件导致的前端 UI 闪烁、时序颠倒与渲染卡顿。
上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `index.ts` | 入口 | 门面导出类型、状态库、Hook 与 UI 胶囊组件 | ✅ |
| `reconnectProtocolTypes.ts` | 契约 | 强类型定义：ReconnectStatus、SessionAtomicSnapshot、LiveDeltaEvent 等 | ✅ |
| `useZeroReplayReconnectStore.ts` | 状态 | Zustand 状态管理库，维护重连状态机、版本号自增与原子快照缓存 | ✅ |
| `useZeroReplayStream.ts` | Hook | 核心流订阅 Hook：原子拉取 Snapshot ➔ 纯 Live 增量 SSE 订阅 ➔ 自动对齐重试 | ✅ |
| `ReconnectStatusPill.tsx` | 视图 | 极简网络状态指示胶囊与手动强制对齐卡片，纯 Lucide SVG 图标，零原生 emoji | ✅ |

## 依赖

- `next-intl` — 国际化词条 `reconnectProtocol`
- `lucide-react` — 矢量图标
- `zustand` — 客户端轻量状态管理
