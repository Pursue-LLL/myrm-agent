# Team Runtime Multi-Surface Cockpit & Conflict Resolution Studio Architecture

## 1. 业务痛点与第一性原理
解决多智能体协同运行期间“看板虽然变绿，但用户无法感知上游前提变更对下游的影响，更无法在模型之间产生方案冲突（如技术架构双活 vs 预算硬顶）时直观干预，最终用户被迫沦为隐形第四人线下反复拉齐对账”的致命交互痛点。

## 2. 核心架构设计
1. **DAG 依赖反应式拓扑画布（Reactive Dependency Canvas）**：
   - `TeamDependencyCanvas.tsx`
   - 直观渲染多智能体有向无环图节点流（Leader ➔ Workers ➔ Finalizer）。
   - **前提变更智能失效警示（Stale Prerequisite）**：当某个上游节点重新生成或修订交付物版本时，下游受影响的连线与节点自动泛起琥珀色光晕，自动拦截盲目无效重跑并展示失效原因。
2. **Leader 矛盾冲突仲裁卡片（Conflict Resolution Trade-off Card）**：
   - `ConflictResolutionModal.tsx`
   - 当检测到业务不可调和冲突时，拒绝让模型自行编造兼容折中案，而是把关键权衡选项（“可用性不可妥协-追加预算” vs “预算不可突破-降级单可用区”）暴露给人类指挥官一键拍板裁决。
3. **交付契约与未决例外检查器（Deliverable & Exception Inspector）**：
   - `DeliverableExceptionDrawer.tsx`
   - 点击任意节点展开右侧抽屉，强制分栏展示【已决事实列表（Decided Facts）】与【未决风险与排除条款（Exceptions）】，杜绝商业风险被摘要糊弄抹平。
4. **团队协调减负度量大盘（Coordination Reduction Telemetry）**：
   - `CoordinationReductionCard.tsx`
   - 动态量化展示协同效益（避免人工口径纠偏次数、节省人工对账时间、阻断下游无效盲跑次数与协同健康分）。
5. **作战全景驾驶舱大屏（Team Runtime Multi-Surface Cockpit）**：
   - `TeamRuntimeMultiSurfaceCockpit.tsx`
   - 聚合状态大屏、DAG 画布、减负大盘、例外抽屉与矛盾仲裁卡片。

## 3. 质量指标与红线
- 单文件全部受控在 200 行以内（远低于 400 行）；
- 严禁 `any` 类型，完备 TypeScript 类型契约；
- 零原生 emoji，全部采用 Lucide 矢量图标；
- 严格遵循语义化 HTML（`<section>`, `<aside>`, `<dialog open>`）杜绝 a11y 警告。
