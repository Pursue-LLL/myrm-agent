# memory-inspector 模块架构

## 架构概述

会话级记忆透视镜、三元认识论可信度指示徽章与一键交互式记忆治理抽屉（Roadmap ⑨ Item 30）。
消除 Agent 长期记忆的黑盒焦虑，赋予用户对记忆可信度的透明洞察与原子治理能力。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `memoryInspectorTypes.ts` | 协议 | 三级认识论等级（assertion/observation/belief）、记忆引用模型与治理操作类型 | ✅ |
| `EpistemicBadge.tsx` | 组件 | 认识论可信度徽章（🟢 断言 / 🔵 观察 / 🟡 信念），支持 compact 与带分值完整模式 | ✅ |
| `MemoryCitationBadge.tsx` | 组件 | 消息气泡轻量挂载的记忆引用徽章（如 `🧠 引用 3 条记忆`），点击唤起透视抽屉 | ✅ |
| `MemoryInspectorDrawer.tsx` | 组件 | 交互式透视抽屉：展示引用的记忆条目、相关度条、证据溯源链，支持「升格」、「纠偏」、「遗忘」三大原子操作 | ✅ |
| `MemoryInspectorContainer.tsx` | 容器 | 全局抽屉挂载容器，监听 `myrm:open-memory-inspector` 事件并与 Store 深度协同 | ✅ |
| `index.ts` | 门面 | 统一导出组件、容器与协议类型 | ✅ |

## 契约要点

- **三级认识论可信度分级**：
  - `assertion`（断言）：用户明确输入的硬性规则/偏好，置信度 1.0；
  - `observation`（观察）：工具在真实环境中探测到的客观事实，置信度 0.85；
  - `belief`（信念）：Agent 自主推断归纳的信息，置信度 0.6，支持一键升格为断言。
- **三大治理操作**：
  - 升格（Promote）：将低置信度信念一键升级为确定性断言；
  - 纠偏（Edit）：内联编辑记忆文本，原子保存；
  - 遗忘（Forget）：彻底物理清除错误或敏感记忆条目。
- **单文件代码质量红线**：单个文件行数严格低于 400 行，零 `any`，零原生 emoji。
