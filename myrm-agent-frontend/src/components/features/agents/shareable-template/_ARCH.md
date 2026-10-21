# Shareable Template & Frictionless Clone Deck Architecture

## 1. 业务目标与定位
实现智能体配置的「一键脱敏分享」与接收者的「零门槛免配置克隆导入」：
- **分享端 (Sharer)**：
  - 自动正则扫描 Agent 配置中的敏感凭据（API Keys、Bearer Tokens、密码、硬编码密钥等）；
  - 零泄露脱敏（Zero-Leak Scrubbing），将私有密钥自动置换为运行时插槽变量（如 `${SERPER_API_KEY}`）；
  - 生成公共只读分发 Slug 链接并支持快速复制。
- **接收端 (Cloner)**：
  - 本地环境依赖自检与智能对齐：检测本地可用模型，若原生底模缺失，自动推导高兼容度平替（Fallback Model）；
  - 技能依赖（Skills）与插槽变量状态直观呈现；
  - 一键执行克隆，写入本地状态，避免繁杂的手工参数复制。

## 2. 核心架构契约
- `shareableTemplateTypes.ts`: 共享模板实体 `BotTemplateEntity`、脱敏审计 `SecretScrubbingAudit`、依赖对齐报告 `DependencyAlignmentReport` 以及克隆执行凭证 `CloneExecutionResult`。
- `useShareableTemplateStore.ts`: 纯逻辑状态管理与算法核，提供 `scrubAgentSecrets` 脱敏器和 `evaluateDependencies` 依赖推导引擎。
- `ShareableTemplateModal.tsx`: 分享者侧模态弹窗，提供安全审计合格证与链接生成。
- `FrictionlessCloneDeck.tsx`: 接收者侧克隆甲板，提供环境自检、平替底模智能匹配与克隆安装动作。

## 3. 设计规范与安全
- 原生语义化 `<dialog open aria-modal="true">` 搭配 `<section role="document">`，遵循 strict a11y 规则。
- 零原生 emoji，全采用统一 Lucide 图标。
- 单文件行数均受控在 250 行以内。
