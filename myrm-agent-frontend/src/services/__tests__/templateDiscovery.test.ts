import { describe, expect, it } from 'vitest';
import {
  normalizeTemplateSearchText,
  resolveTemplateKind,
  templateMatchesCategory,
  templateMatchesSearchQuery,
} from '../templateDiscovery';
import type { TemplateListItem } from '@/services/agent';

describe('templateDiscovery', () => {
  const sampleIndividual: TemplateListItem = {
    id: 'hr_recruiter',
    name: 'HR 招聘与人才发展专家',
    description: '专注岗位置信分析、高转化招聘 JD 编写',
    category: 'office',
    agent_type: 'individual',
    use_cases: ['编写招聘 JD', '设计结构化面试'],
  };

  const sampleTeam: TemplateListItem = {
    id: 'software_dev_squad',
    name: '软件研发专家小队',
    description: '端到端软件需求分析、架构设计与代码实现',
    category: 'team',
    agent_type: 'team',
    members: [
      { role: 'architect', name: '架构师' },
      { role: 'coder', name: '程序员' },
    ],
  };

  it('normalizes search text', () => {
    expect(normalizeTemplateSearchText('  HeLLo  ')).toBe('hello');
  });

  it('resolves template kind accurately', () => {
    expect(resolveTemplateKind('team')).toBe('team');
    expect(resolveTemplateKind('individual')).toBe('individual');
    expect(resolveTemplateKind(undefined)).toBe('individual');
  });

  it('matches search query on name, description and use_cases', () => {
    expect(templateMatchesSearchQuery(sampleIndividual, '招聘')).toBe(true);
    expect(templateMatchesSearchQuery(sampleIndividual, '面试')).toBe(true);
    expect(templateMatchesSearchQuery(sampleIndividual, '不存在的关键词')).toBe(false);
  });

  it('matches category correctly including office and team', () => {
    expect(templateMatchesCategory(sampleIndividual, 'all')).toBe(true);
    expect(templateMatchesCategory(sampleIndividual, '')).toBe(true);
    expect(templateMatchesCategory(sampleIndividual, 'office')).toBe(true);
    expect(templateMatchesCategory(sampleIndividual, 'engineering')).toBe(false);

    expect(templateMatchesCategory(sampleTeam, 'team')).toBe(true);
    expect(templateMatchesCategory(sampleTeam, 'office')).toBe(false);
  });
});
