# group-chat/

## 架构概述

多智能体协作群聊驾驶舱与讨论协商流转可视化组件套件（对标 Hermes Agent v0.21.0 Bot Mode Group Chat）。
打破单智能体 1v1 对话局限，提供群聊房间成员常驻顶栏、输入框 @Agent 联想自适应浮窗、多方接力讨论流与 PASS 静默折叠气泡、以及 needs-you 人权介入呼吸提示栏。

## 文件清单

| 文件 | 职责 |
| --- | --- |
| `groupChatTypes.ts` | 群聊在场成员、讨论流消息、PASS 状态、needs-you 介入及组件 Props 契约 |
| `GroupChatRoomHeader.tsx` | 群聊房间成员常驻顶栏：展示在场 Agent 头像、称号及实时状态灯（idle/reasoning/pass），支持点击头像查看已挂载技能与设定 |
| `AgentMentionPopup.tsx` | 智能输入框 @Agent 联想与定向路由浮窗：模糊搜索智能体名称与职能（如 @sec, @arch），键盘/触控快速点选并指派为主要执行目标 |
| `DeliberationThreadBubble.tsx` | 多方接力讨论流气泡：支持专属角色色彩徽章；将无动作的 PASS 轮次自动收缩为极简胶囊消除刷屏噪音，并可展开判定依据 |
| `InteractiveNeedsYouBanner.tsx` | needs-you 人权介入呼吸提示栏：全宽发光呼吸通知条，展示当前争论焦点、备选方案 Chips 与自定义指令输入框，快速裁决恢复执行 |
| `index.ts` | 统一门面导出 |

## 依赖关系

- `next-intl`: 双语国际化支持（`groupChat` 命名空间）
- `lucide-react`: 零原生 emoji，全量使用 SVG 矢量图标
