# lib/utils/agent-config/

Agent 配置域子包：Agent 到 AgentConfig 的映射构建、依赖校验、技能配置比较与命令绑定的清洗/校验/载荷。**无** React 组件，全部纯函数。

对外唯一门面为 `index.ts` barrel（`@/lib/utils/agent-config`）；组件层消费点一律经 barrel 取公开符号，不深路径引用内部构件。

`__tests__/` 覆盖映射、校验、技能配置比较与命令绑定行为。

- `index.ts`：域门面 barrel — 显式导出清单聚合各文件公开符号，组件层统一导入入口；新增导出须同步本清单（漏加即 typecheck 断裂，编译器护栏）。
- `agentConfigMapper.ts`：Agent 配置映射器 — buildAgentConfig 把运行时 Agent（含模型选择与路由配置）映射为引擎侧 AgentConfig 纯函数。
- `agentConfigValidator.ts`：Agent 依赖校验器 — validateAgentDependencies 逐 skill/agent/MCP 依赖缺失检测、buildMissingDependenciesParts 缺失清单分段文案与 ValidationResult 聚合。
- `commandBindings.ts`：命令绑定纯逻辑 — 命令名/别名清洗（仅字母数字下划线连字符）、逐条校验（补全度与大小写不敏感的重名）、提交载荷（空草稿为 null 以清空服务端绑定）与脏检查，Settings 命令绑定编辑器与 `useAgentCommandBindings` 共用。
- `skillConfigs.ts`：技能个性化配置比较 — areSkillConfigsEqual 缺省字段按默认值计、键顺序无关，Agent 编辑页用它判断技能配置有无未保存改动。

## 依赖

- `@/services/agent`（POS: Agent 服务类型）— Agent / AgentModelSelection 类型。
- `@/store/chat/types`（POS: 聊天类型定义）— AgentConfig / BuiltinToolId 类型。
- `@/store/config/providerTypes`（POS: provider 配置类型）— RoutingConfig / SingleModelSelection 类型。
- `@/store/config/types`（POS: 配置类型定义）— MCPServiceConfig 类型。
- `@/store/skill/types`（POS: Skill 类型定义）— Skill 类型。
