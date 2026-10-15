/**
 * [INPUT] (none)
 * [OUTPUT] skillVersionOriginLabel: 把技能版本的 `created_by` 映射为本地化的来源名称；未知来源返回 null
 * [POS] 技能版本来源的展示词表。服务端写入的 `created_by` 是内部标识，界面只展示用户可理解的来源名称，
 *       不展示原始标识（未知来源直接省略）。
 */

export function skillVersionOriginLabel(createdBy: string, t: (key: string) => string): string | null {
  switch (createdBy) {
    case 'agent_meta_tool':
      return t('createdByAgent');
    case 'settings_editor':
      return t('createdByManual');
    case 'evolution_engine':
      return t('createdBySkillGrowth');
    case 'mutation_rollback':
    case 'batch_rollback':
      return t('createdByRollback');
    case 'batch_import':
      return t('createdByImport');
    case 'llm':
      return t('createdByLlm');
    default:
      return null;
  }
}
