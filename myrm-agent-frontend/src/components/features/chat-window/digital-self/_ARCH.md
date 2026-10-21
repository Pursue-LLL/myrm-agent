# Digital Self Tone Drafting & Outbound Safety Gate Architecture

## 模块定位
本子包负责数字分身拟人化语气草拟回复、同事上下文对齐与外部出站发送绝对确认安全门禁，彻底杜绝 AI 代回复语言生硬冰冷以及 AI 自动化越权发送导致的信息泄密或职场事故。

## 文件拓扑与职责

| 文件 | 地位 | 职责 | I/O/P |
|---|---|---|---|
| `digitalSelfTypes.ts` | 核心契约 | 定义 4 档语气风格、4 档沟通对象关系、渠道类型、草稿状态与出站安全审计日志 | 纯契约导出与配置表 |
| `useDigitalSelfDraftStore.ts` | 门禁状态机 | 管理待审草稿队列、内联快速编辑、语气重写润色、人类显式授权门禁与审计日志 | Zustand 响应式 Store |
| `DigitalSelfToneSelector.tsx` | UI 组件 | 4 档语气风格（严谨正式/职场得体/友好活泼/简明干练）快速切换胶囊 | React 可交互组件 |
| `ToneDraftApprovalCard.tsx` | UI 组件 | 待审草稿卡片，集成原消息摘要、关系标签、参考依据展开、内联编辑与出站硬门禁 | React 核心审核卡片 |
| `DigitalSelfDraftInboxSatellite.tsx` | UI 卫星 | 全局待审草稿悬浮通知条与卡片抽屉，保障出站草稿第一时间触达人工 | React 浮层组件 |
| `index.ts` | 导出出口 | 子包干净聚合出口 | 模块门面 |
