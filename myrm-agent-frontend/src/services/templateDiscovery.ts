/**
 * [INPUT]
 * - services/agent::TemplateListItem (POS: 模板 DTO 类型定义)
 *
 * [OUTPUT]
 * - normalizeTemplateSearchText: 模板搜索标准化。
 * - templateMatchesSearchQuery: 模板搜索命中判定。
 * - resolveTemplateKind: 模板类别归一化（team/individual）。
 *
 * [POS]
 * 专家模板发现层共享纯函数。收敛 TemplateMarket 与 FlowPad 的检索口径，
 * 避免双端逻辑漂移导致召唤体验不一致。
 */
import type { TemplateListItem } from '@/services/agent';
import { WB_TOP20_SKILL_MIGRATION_MAP } from '@/services/skillMigrationMap';

export type ExpertTemplateKind = 'team' | 'individual';

export function resolveTemplateKind(agentType: string | null | undefined): ExpertTemplateKind {
  return agentType === 'team' ? 'team' : 'individual';
}

export function normalizeTemplateSearchText(value: string): string {
  return value.trim().toLowerCase();
}

export function templateMatchesSearchQuery(template: TemplateListItem, query: string): boolean {
  const normalizedQuery = normalizeTemplateSearchText(query);
  if (!normalizedQuery) {
    return true;
  }
  const searchableParts = [
    template.id,
    template.name,
    template.category ?? '',
    template.description ?? '',
    ...(template.use_cases ?? []),
    ...(template.members ?? []).flatMap((member) => [member.name, member.description ?? '']),
  ];

  // 1. 直连匹配
  if (searchableParts.some((part) => normalizeTemplateSearchText(part).includes(normalizedQuery))) {
    return true;
  }

  // 2. 匹配 WorkBuddy 20 大经典高频技能别名/竞品特性映射 (WB 迁移地图增强)
  const matchedWbItems = WB_TOP20_SKILL_MIGRATION_MAP.filter(
    (item) =>
      item.wbSkillId.toLowerCase().includes(normalizedQuery) ||
      item.wbNameZh.toLowerCase().includes(normalizedQuery) ||
      item.wbNameEn.toLowerCase().includes(normalizedQuery) ||
      item.wbScenario.toLowerCase().includes(normalizedQuery),
  );

  if (matchedWbItems.length > 0) {
    const matchedMyrmSkillIds = new Set(matchedWbItems.map((item) => item.myrmSkillId.toLowerCase()));
    // 若当前模板的 ID、预置技能或描述命中被映射的目标技能，则视为命中检索
    const templateId = template.id.toLowerCase();
    const templateDesc = (template.description ?? '').toLowerCase();
    for (const skillId of matchedMyrmSkillIds) {
      if (templateId.includes(skillId) || templateDesc.includes(skillId)) {
        return true;
      }
    }
  }

  return false;
}

export function templateMatchesCategory(template: TemplateListItem, category: string): boolean {
  if (!category || category === 'all') {
    return true;
  }
  if (category === 'team') {
    return template.agent_type === 'team' || template.category === 'team';
  }
  return template.category === category;
}

