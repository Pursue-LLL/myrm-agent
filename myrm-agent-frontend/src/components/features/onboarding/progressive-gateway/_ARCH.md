# ProgressiveDeferredOnboardingAndInstantFirstChatGatewaySuite 架构契约与设计决策

## 1. 业务目标与核心痛点
彻底打破传统个人 AI 助手“把用户当运维、一开局就发一张入场考试卷强行要求配置模型和密钥”的极高劝退门槛。
对标 OpenClaw 2.0 革命性重排理念，落实通用智能体零配置开箱即聊与多合一聚合工作台。

## 2. 核心架构设计与四大支柱
1. **默认通用智能体开箱即聊（Instant First Chat with Default Agent）**：
   - 新用户首次进入系统默认激活开箱即用的轻量推理通道（本地 Ollama 自动嗅探或轻量免费试用配额）；
   - 允许用户无需任何配置，直接在对话框发一句 Prompt，3 秒内验证产品核心价值。
2. **复杂配置按需延迟触发（Deferred Complexity & Contextual Onboarding）**：
   - 拒绝大屏全屏模态阻断；当会话中遇到高级代码沙箱执行或大模型特定微调时，才通过温和内联气泡卡片（`DeferredConfigPrompt`）建议接入 Key 或订阅。
3. **Provider 测试连接失败新手归因指引（钥匙/地址/房间类比落地，子交付 6 专项）**：
   - 服务端与前端双向协同，将底层原始异常（401/403、404、Timeout/DNS、429）归类为四大人性化类别：
     - `key`：钥匙无效（API Key 错误或过期）
     - `url_endpoint`：地址/房间不存在（Base URL 缺少 /v1 或 endpoint 错误）
     - `network`：网络通信受阻（本地代理或防火墙阻断）
     - `quota`：门票点数已耗尽（配额或余额熔断）
   - 在 `ProviderFailureAttributionCard` 中展示清晰的类比、针对性解释与新手排查行动建议。
4. **一键自愈健康诊断探针（Self-Healing Doctor）与五合一工作台**：
   - 自检沙箱隔离环境、本地 Ollama 推理通道、云端网关连通性，提供一键自动修复；
   - 聚合“即时聊天（Chat）、文件工件（Files）、高危审批（Approvals）、全局搜索（Search）与系统设置（Settings）”五合一导航。

## 3. 质量指标与红线守护
- 单文件代码行数严格控制在 230 行以内（远低于 400 行硬顶）；
- 零 `any`，全面采用 TypeScript 静态强类型；
- 零原生 emoji，统一采用 Lucide 矢量图标；
- 所有 `if` 条件逻辑包裹完整大括号；
- a11y 无障碍语义化标签齐全，零控制台警告与报错。
