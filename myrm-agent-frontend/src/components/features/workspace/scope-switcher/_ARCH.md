# Dual-Scope Workspace Switcher & Interactive Discovery Architecture

## 1. 业务目标与痛点直击
解决社区极客 Snar 与 Matthew Campbell 提出的核心痛点：
- **个人 vs 团队协同双空间穿梭 (Top-Level Scope Switcher)**：
  - 彻底破除“个人助手用一套、团队协作必须再买一台电脑”的荒谬成本；
  - 杜绝 OpenClaw 式单网关全员混用导致的私有代码、私密 API Key 与团队公共群聊混淆。
- **Zero-Leak 零泄露硬隔离不变式 (Zero-Leak Isolation Invariant)**：
  - 切换工作区瞬时断开旧会话连接；
  - 彻底擦除当前活动临时上下文（`activeSessionPurged: true`）；
  - 进入团队企业沙箱时自动锁定并隐藏本地私密凭证（`localSecretKeysHidden: true`）；
  - 留存审计日志快照 `ScopeIsolationAudit`。
- **交互式看板与微应用主动发现芯片 (Interactive Discovery Chips)**：
  - 针对自然语言 Agent 中“能力深埋在未知 Prompt 之后”的严重发现度盲区；
  - 在空会话与输入框上方显式推出「📊 生成交互式看板 (Make a Dashboard)」、「⚡ 架构缺陷热力图」、「📈 多智能体工单流」直达芯片。

## 2. 模块契约与职责
- `workspaceScopeTypes.ts`：定义空间类型 `personal` / `team`、企业团队实体 `TeamWorkspaceEntity`、硬隔离审计 `ScopeIsolationAudit` 与发现芯片契约 `DiscoveryChipItem`。
- `useWorkspaceScopeStore.ts`：纯状态管理与隔离看门狗，提供 `switchScope`（执行会话清空与密钥隔离）、`selectDiscoveryChip`（Prompt 模板提取与装配）。
- `WorkspaceScopeSwitcher.tsx`：顶栏全局常驻穿梭胶囊组件，展示当前活跃空间状态、企业团队列表、以及零泄露隔离反馈。
- `InteractiveDashboardDiscoveryChip.tsx`：空会话微应用发现芯片集合与一键装配组件。

## 3. 设计规范与质量红线
- 严格遵循 a11y 规范（带 `aria-expanded` 与原生语义化 `<button>`）。
- 零原生 emoji，统一采用 Lucide 矢量图标。
- 单文件行数均受控在 190 行以内（远低于 400 行红线）。
- 零 `any`，具备完整强类型推导。
