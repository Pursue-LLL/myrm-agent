# Thinking & Permission Control Subpackage Architecture

## 模块定位
本子包负责主对话框内新一代推理模型思考深度（Thinking Budget / Effort）动态调节与智能体三档权限模式（Strict / Semi-Auto / Full-Auto）即时切换，消除冗长思考成本与操作审批割裂体验。

## 文件拓扑与职责

| 文件 | 地位 | 职责 | I/O/P |
|---|---|---|---|
| `thinkingPermissionTypes.ts` | 核心契约 | 定义 Thinking 5 档预算、3 档权限模式与高危 Shell 命令正则检查规则 | 纯契约导出与工具函数 |
| `useThinkingBudgetStore.ts` | 状态机 | 管理推理模型思考预算、Token 预算映射、模型级本地持久化与全局总线同步 | Zustand 响应式 Store |
| `usePermissionTierStore.ts` | 门禁状态机 | 管理三档权限模式切换、只读探测放行、常规文件编辑放行与高危 Shell 阻断判定 | 结合 `shouldAutoApprove` 的安全状态机 |
| `usePermissionAutoApprove.ts` | 桥接 Hook | 将三档权限模式无缝桥接至工具审批流程，实现安全编辑放行与高危命令拦截 | 审批流专用集成 Hook |
| `ThinkingBudgetEffortSlider.tsx` | UI 组件 | 5 档平滑步进滑块与气泡反馈，智能适配模型 reasoning 支持能力 | React 可交互组件 |
| `PermissionModeTierSwitcher.tsx` | UI 组件 | 三档权限胶囊切换器与规则说明浮层，提供零打扰与高安全的可选平衡 | React 可交互组件 |
| `index.ts` | 导出出口 | 子包干净聚合出口 | 模块门面 |
