# Entity Embedded Agent Dock & Signed Record Courier Architecture

## 1. 业务痛点与目标
解决传统通用 AI 助手主界面为一个孤立全局聊天框、用户在查看特定客户/合同/项目卡片时必须手动跳出复制属性贴入输入框两头反复横跳的痛点：
- **业务实体专属原生嵌入式 Agent 抽屉 (In-Entity Agent Dock)**：
  - 每一个业务实体卡片（Contact、Company、Project、Deal、Document）均内嵌专属智能体入口；
  - 抽屉随呼随到，基于实体建立持久化会话线程，刷新无缝恢复。
- **带签名免拷贝实体上下文信使 (SignedRecordToken Courier)**：
  - 前端自动生成带防篡改签名的 `SignedRecordToken`；
  - 实体属性与元数据随令牌自动注入大模型，免除用户手动粘贴复制。
- **实时推演步态与排除线索透明账本 (Step Dossier & Dropped Leads)**：
  - 实时展示搜集的事实与公开核对源；
  - 特别清晰展示其排除了哪些疑似线索及详细原因（The leads it throws away and why，例如同名公司因行业不符被果断丢弃）；
  - 出现多候选人歧义时支持原地人机裁决（In-Place Disambiguation），上下文严密内聚。

## 2. 模块契约与组件职责
- `entityEmbeddedAgentTypes.ts`：定义业务实体快照 `BusinessEntitySnapshot`、防篡改签名令牌 `SignedRecordToken`、推演步态账本 `DossierStepRecord`（含 `discardedReason` 与 `disambiguationOptions`）。
- `useEntityEmbeddedAgentStore.ts`：纯状态管理与签名信使，提供 `generateSignedRecordToken`、`openEntityDock`、`resolveDisambiguation` 与对话流水。
- `EntityAgentTriggerButton.tsx`：挂载在各类业务实体卡片上的胶囊呼出按钮。
- `EntityAgentDock.tsx`：业务实体内嵌专属 Agent 抽屉，展示验签状态、推演透明账本、原地人机裁决与专属问答。

## 3. 设计规范与质量红线
- 原生语义化结构（`<dialog open aria-modal="true">` 搭配 `<section role="document">`），遵循 strict a11y 规范。
- 零原生 emoji，全部采用统一 Lucide 矢量图标。
- 单文件行数均受控在 260 行以内（远低于 400 行上限）。
- 零 `any`，全部具备严格强类型推导。
