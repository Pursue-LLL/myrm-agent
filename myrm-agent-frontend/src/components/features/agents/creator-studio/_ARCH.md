# Visual Bot Creator Studio with Master Inheritance & AI Avatar Mascot Suite Architecture

## 1. 业务痛点与第一性原理
解决传统 Agent 新建面板仅提供冷冰冰的空白表单，导致模型/工具/密钥必须项项重新手动配置，步骤冗长且容易配错；缺乏认知大脑分层指导（不知道轻量清洗任务适合经济型 Flash 模型、深度研报适合推理型模型），造成算力盲目浪费；以及缺少个性化形象与标识，多 Bot 名册冰冷枯燥的交互硬伤。

## 2. 核心架构设计
1. **一键继承主 Agent 核心资产（One-Click Master Setup Inheritance）**：
   - `MasterInheritanceToggleCard.tsx`
   - 默认开启继承开关，一键预填充主 Agent 当前生效的基础大模型、已启用的通用系统工具、配置好的 MCP 扩展服务与环境变量/API Key，支持细粒度勾选。
2. **多层次大脑认知模型分级智能推荐（Cognitive Tiering Guidance）**：
   - `CognitiveTieringSelector.tsx`
   - 分层指引：轻量感知与分拣层（`fast_flash`，高吞吐/超低成本）、通用平衡协作层（`balanced_standard`）、深度推理与专家层（`deep_reasoning`，强逻辑/长思维链），帮助用户建立清晰的算力成本意识。
3. **视觉标识与复古像素吉祥物库（Pixel Mascot Picker & AI Avatar）**：
   - `PixelMascotPicker.tsx`
   - 预置 30+ 款可爱的复古像素电子宠物矢量库（机甲猫、赛博柴犬、机械企鹅、极客小狐狸等）供秒级点选；支持点击【根据人设 AI 一键生图】生成专属拟真头像。
4. **可视化极速新建工坊模态面板（Visual Bot Creator Studio Modal）**：
   - `VisualBotCreatorStudioModal.tsx`
   - 聚合基础人设与 SOUL.md、资产继承、大脑认知层级与视觉标识装配流，一键极速创建并激活智能体。

## 3. 质量指标与红线
- 单文件全部受控在 220 行以内（远低于 400 行）；
- 严禁 `any` 类型，完整 TypeScript 类型定义；
- 零原生 emoji，全部采用 Lucide 矢量图标；
- 严格遵循语义化 HTML 规范，杜绝 a11y 警告。
