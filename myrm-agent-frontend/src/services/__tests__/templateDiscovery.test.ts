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

    const sampleCommerce: TemplateListItem = {
      id: 'storefront_shopper_agent',
      name: '智能导购伙伴',
      description: '全能电商导购与变体收敛',
      category: 'commerce',
      agent_type: 'individual',
      use_cases: ['多规格选品', '购物车小计计算'],
    };
    expect(templateMatchesCategory(sampleCommerce, 'commerce')).toBe(true);
    expect(templateMatchesCategory(sampleCommerce, 'office')).toBe(false);
    expect(templateMatchesSearchQuery(sampleCommerce, '导购')).toBe(true);
    expect(templateMatchesSearchQuery(sampleCommerce, '变体')).toBe(true);
  });

  it('matches search query via WorkBuddy top 20 migration map alias', () => {
    const meetingTemplate: TemplateListItem = {
      id: 'meeting_assistant',
      name: '智能会议小助手',
      description: '基于 voice-memo-synthesizer 提取会议待办',
      category: 'office',
      agent_type: 'individual',
    };
    // 搜索 WB 迁移条目别名 "wb-meeting-minutes" 或中文 "会议纪要"
    expect(templateMatchesSearchQuery(meetingTemplate, 'wb-meeting-minutes')).toBe(true);
    expect(templateMatchesSearchQuery(meetingTemplate, '会议纪要')).toBe(true);
  });

  it('matches commerce category and id/category search queries', () => {
    const shopperTemplate: TemplateListItem = {
      id: 'storefront_shopper_agent',
      name: '智能导购伙伴',
      description: '面向消费者的垂直领域智能导购专家，精通多规格变体解析与购物车治理',
      category: 'commerce',
      agent_type: 'individual',
      use_cases: ['跑鞋选品与尺码收敛', '商品比价与政策解读'],
    };

    expect(templateMatchesCategory(shopperTemplate, 'commerce')).toBe(true);
    expect(templateMatchesCategory(shopperTemplate, 'office')).toBe(false);
    expect(templateMatchesSearchQuery(shopperTemplate, 'storefront')).toBe(true);
    expect(templateMatchesSearchQuery(shopperTemplate, 'commerce')).toBe(true);
    expect(templateMatchesSearchQuery(shopperTemplate, '导购')).toBe(true);

    const merchantTemplate: TemplateListItem = {
      id: 'backoffice_merchant_agent',
      name: '店铺经营参谋',
      description: '面向商家运营的经营参谋智能体，精通全店销售大盘分析、库存缺货预警、两阶段调价审批门禁与合规促销策划',
      category: 'commerce',
      agent_type: 'individual',
      use_cases: ['销售大盘分析', '合规调价与利润保护'],
    };

    expect(templateMatchesCategory(merchantTemplate, 'commerce')).toBe(true);
    expect(templateMatchesCategory(merchantTemplate, 'office')).toBe(false);
    expect(templateMatchesSearchQuery(merchantTemplate, 'backoffice')).toBe(true);
    expect(templateMatchesSearchQuery(merchantTemplate, 'merchant')).toBe(true);
    expect(templateMatchesSearchQuery(merchantTemplate, '经营参谋')).toBe(true);
  });
});
