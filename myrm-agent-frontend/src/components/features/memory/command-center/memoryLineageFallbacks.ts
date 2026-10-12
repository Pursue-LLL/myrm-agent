/**
 * [INPUT]
 * @/services/memory::(Lineage DTOs)
 *
 * [OUTPUT]
 * Constants: FALLBACK_LINEAGE_STATS, FALLBACK_TOPOLOGY_GRAPH,
 *            FALLBACK_LINEAGE_TRAIL, FALLBACK_REORGANIZATION_REPORT
 *
 * [POS]
 * High-fidelity fallbacks for Item 126 Graph Memory Reorganization & Lineage Traceability Suite.
 * Guarantees resilient WebUI preview and uninterrupted offline experience.
 * Strict typing applied: Zero `any` types. Single file < 200 lines.
 */

import type {
  LineageStatsDTO,
  MemoryTopologyGraphDTO,
  MemoryLineageTrailDTO,
  ReorganizationBatchResponse,
} from '@/services/memory';

export const FALLBACK_LINEAGE_STATS: LineageStatsDTO = {
  total_nodes: 5,
  active_nodes: 4,
  superseded_nodes: 1,
  reverted_nodes: 0,
  total_edges: 4,
  max_depth: 2,
};

export const FALLBACK_TOPOLOGY_GRAPH: MemoryTopologyGraphDTO = {
  nodes: [
    {
      node_id: 'mem_pref_coffee_v1',
      lineage_root_id: 'lineage_pref_beverage',
      version: 1,
      subject: 'User',
      predicate: 'prefers_morning_drink',
      object_value: 'Black Americano',
      content: 'User prefers hot black americano with zero sugar for work mornings.',
      confidence: 0.92,
      status: 'superseded',
      created_at: '2026-10-01T08:00:00Z',
      updated_at: '2026-10-04T10:00:00Z',
      source_session_id: 'sess_onboarding_001',
      evidence_quote: 'I only drink black americano every morning.',
    },
    {
      node_id: 'mem_pref_coffee_v2',
      lineage_root_id: 'lineage_pref_beverage',
      version: 2,
      subject: 'User',
      predicate: 'prefers_morning_drink',
      object_value: 'Iced Oat Latte',
      content: 'User switched to iced oat latte due to mild stomach discomfort with black coffee.',
      confidence: 0.98,
      status: 'active',
      created_at: '2026-10-04T10:00:00Z',
      updated_at: '2026-10-04T10:00:00Z',
      source_session_id: 'sess_diet_update_042',
      evidence_quote: 'Black coffee was causing stomach reflux, so I switched to oat latte.',
    },
    {
      node_id: 'mem_stack_python',
      lineage_root_id: 'lineage_stack_python',
      version: 1,
      subject: 'Tech Stack',
      predicate: 'language_standard',
      object_value: 'Python 3.12+',
      content: 'Project adheres strictly to modern Python type hint conventions.',
      confidence: 0.95,
      status: 'active',
      created_at: '2026-10-01T08:00:00Z',
      updated_at: '2026-10-01T08:00:00Z',
      source_session_id: 'sess_init_arch',
    },
    {
      node_id: 'mem_stack_pydantic',
      lineage_root_id: 'lineage_stack_pydantic',
      version: 1,
      subject: 'Tech Stack Pydantic',
      predicate: 'schema_validation',
      object_value: 'Pydantic V2 strict models with zero Any',
      content: 'All API contracts must use Pydantic V2 frozen models with no Any typing allowed.',
      confidence: 0.99,
      status: 'active',
      created_at: '2026-10-07T14:00:00Z',
      updated_at: '2026-10-07T14:00:00Z',
      source_session_id: 'sess_arch_review',
    },
  ],
  edges: [
    {
      edge_id: 'edge_sup_coffee_2_1',
      source_node_id: 'mem_pref_coffee_v2',
      target_node_id: 'mem_pref_coffee_v1',
      relation_type: 'supersedes',
      weight: 1.0,
      rationale: 'Explicit user preference update superseding black americano.',
      created_at: '2026-10-04T10:00:00Z',
    },
    {
      edge_id: 'edge_sub_pydantic_python',
      source_node_id: 'mem_stack_python',
      target_node_id: 'mem_stack_pydantic',
      relation_type: 'subsumption',
      weight: 0.91,
      rationale: 'Pydantic strict typing is a domain subsumption under Python 3.12+ type contracts.',
      created_at: '2026-10-07T14:00:00Z',
    },
  ],
};

export const FALLBACK_LINEAGE_TRAIL: MemoryLineageTrailDTO = {
  target_node: FALLBACK_TOPOLOGY_GRAPH.nodes[1],
  lineage_root_id: 'lineage_pref_beverage',
  ancestor_nodes: [FALLBACK_TOPOLOGY_GRAPH.nodes[0]],
  descendant_nodes: [],
  steps: [
    {
      step_index: 1,
      node: FALLBACK_TOPOLOGY_GRAPH.nodes[0],
      relation_to_target: 'supersedes',
      rationale: 'Initial recorded preference for morning black coffee.',
      timestamp: '2026-10-01T08:00:00Z',
    },
    {
      step_index: 2,
      node: FALLBACK_TOPOLOGY_GRAPH.nodes[1],
      relation_to_target: null,
      rationale: 'User preference updated to oat latte due to stomach comfort.',
      timestamp: '2026-10-04T10:00:00Z',
    },
  ],
  relation_edges: [FALLBACK_TOPOLOGY_GRAPH.edges[0]],
  depth: 1,
  is_latest: true,
};

export const FALLBACK_REORGANIZATION_REPORT: ReorganizationBatchResponse = {
  batch_id: 'reorg_demo_98af',
  analyzed_nodes_count: 4,
  created_edges_count: 1,
  superseded_nodes_count: 0,
  deductions_count: 0,
  edges: [FALLBACK_TOPOLOGY_GRAPH.edges[1]],
  created_at: '2026-10-08T12:00:00Z',
};
