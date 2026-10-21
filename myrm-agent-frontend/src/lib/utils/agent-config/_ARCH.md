# lib/utils/agent-config/

Agent 配置域子包：Agent 到 AgentConfig 的映射构建与依赖校验。**无** React 组件，全部纯函数。

对外唯一门面为 `index.ts` barrel（`@/lib/utils/agent-config`）；组件层消费点一律经 barrel 取公开符号，不深路径引用内部构件。

`__tests__/` 覆盖映射与校验行为。

- `index.ts`：域门面 barrel — 显式导出清单聚合两文件公开符号，组件层统一导入入口；新增导出须同步本清单（漏加即 typecheck 断裂，编译器护栏）。
- `agentConfigMapper.ts`：Agent 配置映射器 — buildAgentConfig 把运行时 Agent（含模型选择与路由配置）映射为引擎侧 AgentConfig 纯函数。
- `agentConfigValidator.ts`：Agent 依赖校验器 — validateAgentDependencies 逐 skill/agent/MCP 依赖缺失检测、buildMissingDependenciesParts 缺失清单分段文案与 ValidationResult 聚合。

## 依赖

- `@/services/agent`（POS: Agent 服务类型）— Agent / AgentModelSelection 类型。
- `@/store/chat/types`（POS: 聊天类型定义）— AgentConfig / BuiltinToolId 类型。
- `@/store/config/providerTypes`（POS: provider 配置类型）— RoutingConfig / SingleModelSelection 类型。
- `@/store/config/types`（POS: 配置类型定义）— MCPServiceConfig 类型。
- `@/store/skill/types`（POS: Skill 类型定义）— Skill 类型。
