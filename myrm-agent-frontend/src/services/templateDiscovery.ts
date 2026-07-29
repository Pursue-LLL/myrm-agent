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
    template.name,
    template.description ?? '',
    ...(template.use_cases ?? []),
    ...((template.members ?? []).flatMap((member) => [member.name, member.description ?? ''])),
  ];
  return searchableParts.some((part) => normalizeTemplateSearchText(part).includes(normalizedQuery));
}
