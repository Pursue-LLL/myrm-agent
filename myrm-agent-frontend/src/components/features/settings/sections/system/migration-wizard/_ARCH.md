# Migration Wizard & Zero-SSH Ecosystem Transpiler Architecture

## 1. 业务痛点与目标
解决 Claire Vo 与极客 Bryan Wilson 高度吐槽的“从 OpenClaw / Hermes 迁移资产需要用 Tailscale+SSH 翻山越岭搞外科手术式迁移”的痛点：
- **本地竞品生态足迹静默雷达扫描 (Local Agent Footprint Scanner)**：
  - 自动探针常见用户目录（`~/.openclaw`、`~/.hermes`、`~/.cursor`、`.claude`）；
  - 毫秒级提取已配置智能体数、自研技能脚本数与 MCP 工具服务；
- **跨生态无损智能转译引擎 (Zero-Loss Ecosystem Transpiler)**：
  - 自动将旧版 Prompt 转换为 Myrm `AgentProfile`；
  - 规范化转换为 Myrm 标准技能（保留内部执行脚本与权限）；
  - 自动将 `mcp.json` 转换为 Myrm MCP 工具中心配置；
- **一键搬家引导与确认抽屉 (MigrationWizardDrawer)**：
  - 顶部关怀横幅 `MigrationScanBanner.tsx` 主动提醒用户已有资产；
  - 抽屉展示分类资产勾选、冲突处理与转译进度条，1 秒完成升级。

## 2. 模块契约与职责
- `migrationWizardTypes.ts`：生态来源枚举 `EcosystemSource`、探测资产实体 `DetectedAgentAsset` / `DetectedSkillAsset` / `DetectedMcpAsset`、雷达报告 `ScanRadarReport` 与迁移进度 `MigrationExecutionProgress`。
- `useMigrationWizardStore.ts`：纯状态管理与转译流水线，提供资产勾选、全选、步进无损转译动作。
- `MigrationScanBanner.tsx`：主界面顶部主动关怀探测横幅。
- `MigrationWizardDrawer.tsx`：可视化一键搬家确认抽屉，提供分类勾选与实时进度呈现。

## 3. 设计规范与质量红线
- 原生语义化结构（`<dialog open aria-modal="true">` 搭配 `<section role="document">`），遵循 strict a11y 规范。
- 零原生 emoji，全部采用 Lucide 矢量图标。
- 单文件行数均受控在 260 行以内（远低于 400 行上限）。
- 零 `any`，全部具备强类型约束。
