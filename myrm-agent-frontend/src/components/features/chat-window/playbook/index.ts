/**
 * [INPUT]
 * - ./ModelOrchestrationPlaybookChip (POS: 发现胶囊)
 * - ./ModelOrchestrationPlaybookDialog (POS: 编排看板弹窗)
 * - ./modelOrchestrationRecipes (POS: 预设定义与匹配引擎)
 *
 * [OUTPUT]
 * - ModelOrchestrationPlaybookChip: 导出发现胶囊
 * - ModelOrchestrationPlaybookDialog: 导出编排弹窗
 * - MODEL_ORCHESTRATION_RECIPES: 导出三大黄金预设
 *
 * [POS]
 * 模型编排最佳实践子包门面导出。对齐架构分层规范，提供全模块唯一聚合出口。
 */

export { ModelOrchestrationPlaybookChip } from './ModelOrchestrationPlaybookChip';
export { ModelOrchestrationPlaybookDialog } from './ModelOrchestrationPlaybookDialog';
export {
  MODEL_ORCHESTRATION_RECIPES,
  resolveRecipeReadiness,
  applyOrchestrationRecipe,
  applyRecipeToAgentModelSelection,
  type ModelOrchestrationRecipe,
  type RecipeTierId,
  type RecipeReadiness,
} from './modelOrchestrationRecipes';
