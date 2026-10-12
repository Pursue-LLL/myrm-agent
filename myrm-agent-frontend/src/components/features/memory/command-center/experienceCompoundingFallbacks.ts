/**
 * Fallback fixtures and offline simulation data for Experience Compounding & Knowledge Condensation.
 * Supplies graceful mock telemetry when offline or server endpoints are unavailable.
 */

import {
  CompoundedExperienceItemDTO,
  GoldenRuleDTO,
  CondensationResponseDTO,
  AnnealingResponseDTO,
  ExperienceCompoundingStatsResponse,
} from '@/services/memory/experienceCompounding';

export const mockCompoundingStats: ExperienceCompoundingStatsResponse = {
  total_items: 6,
  active_items: 4,
  condensed_items: 2,
  cold_tiered_items: 1,
  golden_rules_count: 1,
  average_compounded_weight: 1.42,
};

export const mockActiveExperiences: CompoundedExperienceItemDTO[] = [
  {
    item_id: 'exp-mock-1',
    content: '前端组件样式排版优先采用 TailwindCSS 原子化紧凑类名',
    topic: 'frontend',
    base_weight: 1.0,
    compounded_weight: 1.65,
    peak_weight: 1.65,
    hit_count: 8,
    adoption_count: 5,
    state: 'active',
    half_life_days: 35.0,
    is_pinned: false,
    is_temporary: false,
    tags: ['ui', 'tailwind', 'layout'],
  },
  {
    item_id: 'exp-mock-2',
    content: '前端布局优先采用 Flexbox 弹性响应式结构，保证移动端自适应',
    topic: 'frontend',
    base_weight: 1.0,
    compounded_weight: 1.48,
    peak_weight: 1.48,
    hit_count: 6,
    adoption_count: 3,
    state: 'active',
    half_life_days: 28.0,
    is_pinned: false,
    is_temporary: false,
    tags: ['ui', 'flexbox'],
  },
  {
    item_id: 'exp-mock-3',
    content: 'Python 代码严格禁止使用 Any 类型注解，必须提供具体强类型契约',
    topic: 'quality',
    base_weight: 1.5,
    compounded_weight: 2.5,
    peak_weight: 2.5,
    hit_count: 24,
    adoption_count: 18,
    state: 'active',
    half_life_days: 120.0,
    is_pinned: true,
    is_temporary: false,
    tags: ['python', 'typing', 'pinned'],
  },
  {
    item_id: 'exp-mock-4',
    content: '调试临时代理端口 8099 偶发 ECONNREFUSED 现象记录',
    topic: 'debug',
    base_weight: 1.0,
    compounded_weight: 0.85,
    peak_weight: 1.0,
    hit_count: 2,
    adoption_count: 0,
    state: 'active',
    half_life_days: 3.0,
    is_pinned: false,
    is_temporary: true,
    tags: ['temporary', 'proxy'],
  },
];

export const mockGoldenRules: GoldenRuleDTO[] = [
  {
    rule_id: 'rule-mock-fe-01',
    topic: 'frontend',
    rule_statement: '[FRONTEND核心准则] 前端组件排版优先采用 TailwindCSS 原子类与 Flexbox 响应式弹性布局',
    rationale: '由 2 条经过多次高频验证的原始样式与布局偏好碎片聚合提炼而成',
    confidence_score: 0.78,
    source_fragment_ids: ['frag-src-1', 'frag-src-2'],
  },
];

export const mockCondensationResponse: CondensationResponseDTO = {
  report_id: 'condense-mock-77a',
  rules_generated: mockGoldenRules,
  clusters_found: 1,
  fragments_archived: 2,
  compression_ratio: 0.5,
  details: ['Synthesized rule rule-mock-fe-01 from 2 fragments under topic [frontend].'],
};

export const mockAnnealingResponse: AnnealingResponseDTO = {
  report_id: 'anneal-mock-88b',
  inspected_count: 4,
  active_lease_exempt_count: 1,
  cold_tiered_count: 1,
  decayed_items: ['Demoted item [exp-mock-4] (topic: debug) to cold storage (weight: 0.18).'],
};
