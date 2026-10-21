/**
 * [INPUT]
 * @/services/memory::MemoryCubeDTO, MountPolicyDTO, CubeMatrixOverviewDTO, CubeRecordDTO
 *
 * [OUTPUT]
 * Fallback baseline mock topologies and records for Memory Cube Scoped Isolation Suite (Item 124).
 *
 * [POS]
 * Client-side offline fallback and unit test fixtures for Item 124.
 * Strict typing applied: No `any` types allowed. Single file < 200 lines.
 */

import type {
  CubeMatrixOverviewDTO,
  CubeRecordDTO,
  MemoryCubeDTO,
  MountPolicyDTO,
} from '@/services/memory';

export const FALLBACK_MEMORY_CUBES: MemoryCubeDTO[] = [
  {
    cube_id: 'cube-global-shared',
    name: 'Global Core Principles',
    scope_type: 'global_shared',
    owner_id: null,
    description: 'System-wide invariants, architecture rules, and non-negotiable standards.',
    is_read_only: true,
    item_count: 2,
    created_at: 1775600000,
    updated_at: 1775600000,
  },
  {
    cube_id: 'cube-proj-open-perplexity',
    name: 'OpenPerplexity Workspace',
    scope_type: 'project_workspace',
    owner_id: '/workspace/open-perplexity',
    description: 'Project-level specs, team conventions, and cross-session roadmap notes.',
    is_read_only: false,
    item_count: 3,
    created_at: 1775601000,
    updated_at: 1775601500,
  },
  {
    cube_id: 'cube-agent-architect-private',
    name: 'Architect Agent Private Journal',
    scope_type: 'agent_private',
    owner_id: 'agent-architect',
    description: 'Private reasoning scratchpad, temporary hypotheses, and uncommitted thoughts.',
    is_read_only: false,
    item_count: 4,
    created_at: 1775602000,
    updated_at: 1775602200,
  },
  {
    cube_id: 'cube-task-tmp-build',
    name: 'Ephemeral Build Context',
    scope_type: 'ephemeral_task',
    owner_id: 'task-19486',
    description: 'Volatile per-task memory buffer scheduled for disposal after completion.',
    is_read_only: false,
    item_count: 1,
    created_at: 1775603000,
    updated_at: 1775603100,
  },
];

export const FALLBACK_MOUNT_POLICIES: MountPolicyDTO[] = [
  {
    agent_id: 'agent-architect',
    readable_cube_ids: [
      'cube-global-shared',
      'cube-proj-open-perplexity',
      'cube-agent-architect-private',
    ],
    writable_cube_ids: ['cube-agent-architect-private'],
    default_write_cube_id: 'cube-agent-architect-private',
    strict_isolation: true,
  },
  {
    agent_id: 'agent-reviewer',
    readable_cube_ids: ['cube-global-shared', 'cube-proj-open-perplexity'],
    writable_cube_ids: ['cube-proj-open-perplexity'],
    default_write_cube_id: 'cube-proj-open-perplexity',
    strict_isolation: true,
  },
];

export const FALLBACK_SAMPLE_RECORDS: Record<string, CubeRecordDTO[]> = {
  'cube-global-shared': [
    {
      record_id: 'rec-glob-1',
      cube_id: 'cube-global-shared',
      content: 'Rule 1: Always enforce clean architecture and zero any types.',
      metadata: { priority: 'critical', layer: 'system' },
      created_at: 1775600100,
    },
    {
      record_id: 'rec-glob-2',
      cube_id: 'cube-global-shared',
      content: 'Rule 2: Strictly separate read-only shared knowledge from agent write partitions.',
      metadata: { priority: 'high', layer: 'governance' },
      created_at: 1775600200,
    },
  ],
  'cube-proj-open-perplexity': [
    {
      record_id: 'rec-proj-1',
      cube_id: 'cube-proj-open-perplexity',
      content: 'Item 124 Memory Cube addresses multi-agent cross-talk via MemOS compartments.',
      metadata: { item_id: 124, status: 'in-progress' },
      created_at: 1775601100,
    },
  ],
  'cube-agent-architect-private': [
    {
      record_id: 'rec-arch-1',
      cube_id: 'cube-agent-architect-private',
      content: 'Internal theory: Federated query across readable cubes achieves zero leakage.',
      metadata: { private: true },
      created_at: 1775602100,
    },
  ],
};

export const FALLBACK_CUBE_MATRIX_OVERVIEW: CubeMatrixOverviewDTO = {
  cubes: FALLBACK_MEMORY_CUBES,
  policies: FALLBACK_MOUNT_POLICIES,
  total_cubes: FALLBACK_MEMORY_CUBES.length,
  total_records: 10,
  system_healthy: true,
};
