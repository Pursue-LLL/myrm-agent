/**
 * [INPUT]
 * @/services/memory::GrowthDiaryEntryDTO, DreamCognitiveOverviewDTO,
 *                    CognitiveConsolidationReportDTO, DreamCognitiveActionDTO
 *
 * [OUTPUT]
 * Fallback fixtures for Dream Cognitive Consolidation & Growth Diary Suite (Item 125 P1).
 *
 * [POS]
 * Client-side offline fallback and unit test fixtures for Item 125.
 * Strict typing applied: No `any` types allowed. Single file < 200 lines.
 */

import type {
  CognitiveConsolidationReportDTO,
  DreamCognitiveActionDTO,
  DreamCognitiveOverviewDTO,
  GrowthDiaryEntryDTO,
} from '@/services/memory';

export const FALLBACK_SAMPLE_ACTIONS: DreamCognitiveActionDTO[] = [
  {
    action_id: 'act-cog-001',
    action_type: 'create',
    target_type: 'rule',
    target_id: null,
    source_fact_ids: ['fact-101', 'fact-102'],
    payload_statement:
      'Rule: Enforce concrete Type Hints across all Python/TS files; strictly avoid Any types.',
    deduction: {
      hypothetical_query: 'How to declare interfaces in new services?',
      improved_response_reasoning:
        'Prevents loose types and eliminates runtime bugs by mandating explicit models.',
      confidence_gain: 0.35,
    },
    confidence: 0.95,
    cube_id: 'cube-global-shared',
  },
  {
    action_id: 'act-cog-002',
    action_type: 'update',
    target_type: 'insight',
    target_id: 'ins-sec-01',
    source_fact_ids: ['fact-201'],
    payload_statement:
      'Insight: Memory Cubes provide strict read/write decoupled mounting to eliminate cross-talk.',
    deduction: {
      hypothetical_query: 'Can agent-architect write to shared workspace norms?',
      improved_response_reasoning:
        'Immediately blocks unauthorized mutations and routes writes to private compartments.',
      confidence_gain: 0.4,
    },
    confidence: 0.92,
    cube_id: 'cube-proj-open-perplexity',
  },
];

export const FALLBACK_GROWTH_DIARIES: GrowthDiaryEntryDTO[] = [
  {
    diary_id: 'diary-growth-001',
    title: 'Cognitive Leap in Typing Rigor: Internalizing Concrete Schemas',
    summary:
      'Reflected across sessions 101-105: developer values deterministic stability over convenience.',
    reflective_narrative:
      'During background dream reflection, analyzed recurring code reviews. Noticed user repeatedly corrects vague type assertions. Transitioned internal mental model to prioritize strict typing, single-responsibility file boundaries, and clean architectural separation.',
    motive_type: 'frequency',
    themes: ['Type Safety', 'Clean Architecture', 'Engineering Discipline'],
    cube_id: 'cube-global-shared',
    generated_actions: FALLBACK_SAMPLE_ACTIONS,
    created_at: '2026-10-08T11:30:00Z',
  },
  {
    diary_id: 'diary-growth-002',
    title: 'Mind Evolution: Multi-Agent Isolation and Zero Cross-Talk Governance',
    summary:
      'Discovered that unpartitioned memory leads to cognitive interference between sub-agents.',
    reflective_narrative:
      'Observed that multiple agents concurrently modifying global memory leads to hallucination and conflicting directives. Formed invariant: all sub-agents must mount read-only shared principles and write exclusively to dedicated private Memory Cubes.',
    motive_type: 'conflict',
    themes: ['Multi-Agent Governance', 'Memory Cube Isolation', 'Zero Contamination'],
    cube_id: 'cube-proj-open-perplexity',
    generated_actions: [FALLBACK_SAMPLE_ACTIONS[1]],
    created_at: '2026-10-08T10:15:00Z',
  },
];

export const FALLBACK_DREAM_OVERVIEW: DreamCognitiveOverviewDTO = {
  total_diaries: 2,
  total_actions: 3,
  active_cubes: ['cube-global-shared', 'cube-proj-open-perplexity'],
  latest_run_id: 'run-dream-20261008-01',
};

export const FALLBACK_CONSOLIDATION_REPORT: CognitiveConsolidationReportDTO = {
  run_id: 'run-dream-live-001',
  cube_id: 'cube-proj-open-perplexity',
  timestamp: '2026-10-08T12:00:00Z',
  duration_ms: 124.5,
  input_fact_count: 5,
  clusters_formed: 2,
  actions_generated: 2,
  diary_entries: [FALLBACK_GROWTH_DIARIES[0]],
};
