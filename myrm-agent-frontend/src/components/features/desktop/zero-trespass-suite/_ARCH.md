# DesktopZeroTrespassAutostartGuardWithCostBudgetHUDAndDeltaOtaSuite 架构契约与设计决策

## 1. 业务目标与反面痛点
对标阿里千问办公 QwenWork 与 Google Foresight 的反面教训：
- 消除“开机自启关掉后每次打开又偷偷重新勾上”的流氓越界；
- 消除“额外安装 4 小时后台保活任务、退出后又被拉起”的流氓行为；
- 消除“暗箱扣费、偷烧 Token 替用户做决定、以及国内版给 Max 国际版暗降 Flash”的信任危机；
- 消除“天天拉几百兆全量安装包干吐血流量”的低劣 OTA 体验。

## 2. 核心架构设计与四大支柱
1. **零越界自启动授权契约（Zero-Trespass Autostart Guard）**：
   - 采用显式单向授权契约，严格遵循 `neverOverrideSystemChoice: true`；用户在系统层或设置页关闭后，任何应用启动与热更新绝不重新篡改注册表或 LaunchAgents；
   - 提供后台常驻守护进程透明监控（PID、CPU%、内存 MB、网络流量），提供一键 `Kill & Clean` 彻底清理退出，绝不留僵尸常驻进程。
2. **全链路 Token 成本预算沙盒与真实模型防降级遥测（Cost Budget Gate & Anti-Downgrade Telemetry）**：
   - 任务事前测算 Token 与成本预估；超过预设阈值（$0.50）主动触发阻断确认闸门；
   - 物理真实模型防降级遥测：不可篡改地标注真实物理模型 ID、提供商与毫秒级延迟；物理模型不一致时立即报警；
   - 支持 BYOK 自带 Key 零差价直通通道。
3. **“帮你省了哪一步”价值量化面板（Step-Saver Quantification）**：
   - 任务结项清晰量化：本次自动省去了哪几步重复劳动、预计节省人工耗时分钟数；
   - 声明诚实能力边界（Honest Capability Boundary），杜绝过度吹嘘。
4. **Zstd 微差量静默热更指示器（Micro-Differential Delta OTA）**：
   - 每天仅拉取数十 KB 差量更新包，免下载数百 MB 全量安装包，节省 99.98% 流量。

## 3. 质量指标与红线守护
- 单文件代码行数严格控制在 230 行以内（远低于 400 行硬顶）；
- 零 `any`，全面采用 TypeScript 静态强类型；
- 零原生 emoji，统一采用 Lucide 矢量图标；
- 所有 `if` 条件逻辑包裹完整大括号；
- a11y 无障碍语义化标签齐全，零控制台警告与报错。
