/**
 * [POS]
 * Subagent data domain facade. Explicit re-export list is the compiler-enforced
 * public surface: adding an export inside the package without listing it
 * here leaves it package-private (typecheck breaks consumer imports instead
 * of silently leaking symbols).
 */
export type { SortMode, FilterMode } from './subagentTree';
export type { TreeNode, SubtreeAggregate, TreeTotals } from './subagentTree';
export {
  buildTree,
  extractCostUsd,
  extractTotalTokens,
  extractBudgetTokens,
  extractMaxCostUsd,
  aggregate,
  treeTotals,
  sortNodes,
  filterNodes,
  flattenTree,
  fmtCost,
  fmtTokens,
  fmtBudgetCost,
} from './subagentTree';

export type { TopologyTone } from './taskTopologyModel';
export type { TopologyNodeData, TopologyEdgeData, TopologyModel } from './taskTopologyModel';
export {
  MAX_LABEL_LENGTH,
  truncateLabel,
  toneForStatus,
  buildTopologyModel,
  buildFissionTopologyModel,
  buildMergedTopologyModel,
} from './taskTopologyModel';

export type { StageCategory } from './stageTaskCount';
export type { StageProgressItem, StageTaskCountSummary } from './stageTaskCount';
export { classifyNodeStage, deriveStageTaskCounts } from './stageTaskCount';
